"""
Integração com API Baileys para WhatsApp
Sistema de cobrança e envio de mensagens via WhatsApp Web
"""

import os
import requests
import logging
from datetime import datetime, timedelta
import json
import time
from typing import Dict, Any, Optional, List
import base64
from io import BytesIO
import qrcode
from utils import agora_br, formatar_datetime_br

logger = logging.getLogger(__name__)

class BaileysAPI:
    def __init__(self):
        """Inicializa a integração com Baileys API"""
        self.base_url = os.getenv('BAILEYS_API_URL', 'http://localhost:3000')
        self.api_key = os.getenv('BAILEYS_API_KEY', '')
        # Remover sessão padrão fixa - será definida por usuário
        self.default_session = os.getenv('BAILEYS_SESSION', 'bot_clientes')  # Apenas fallback
        self.timeout = int(os.getenv('BAILEYS_TIMEOUT', '30'))
        self.max_retries = int(os.getenv('BAILEYS_MAX_RETRIES', '3'))
        self.retry_delay = int(os.getenv('BAILEYS_RETRY_DELAY', '5'))
        
        # Configurações de envio
        self.message_delay = int(os.getenv('BAILEYS_MESSAGE_DELAY', '2'))
        self.auto_reconnect = os.getenv('BAILEYS_AUTO_RECONNECT', 'true').lower() == 'true'
        
        # Headers padrão
        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Bot-Clientes/1.0'
        }
        
        if self.api_key:
            self.headers['Authorization'] = f'Bearer {self.api_key}'
        
        # Cache de status
        self._status_cache = {}
        self._cache_timeout = 300  # 5 minutos
        
        logger.info(f"Baileys API inicializada: {self.base_url}")
    
    def get_user_session(self, chat_id_usuario: int) -> str:
        """Gera nome de sessão específico para o usuário"""
        return f"user_{chat_id_usuario}"
    
    def _make_request(self, endpoint: str, method: str = 'GET', data: Dict = None, retries: int = None) -> Dict:
        """Faz requisição HTTP para a API Baileys"""
        if retries is None:
            retries = self.max_retries
        
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        for attempt in range(retries + 1):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=self.headers, timeout=self.timeout, params=data)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=self.headers, timeout=self.timeout, json=data)
                elif method.upper() == 'PUT':
                    response = requests.put(url, headers=self.headers, timeout=self.timeout, json=data)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=self.headers, timeout=self.timeout)
                else:
                    raise ValueError(f"Método HTTP não suportado: {method}")
                
                # Log da requisição
                logger.debug(f"Baileys API Request: {method} {url} - Status: {response.status_code}")
                
                # Verificar resposta
                if response.status_code == 200:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        return {'success': True, 'data': response.text}
                elif response.status_code == 401:
                    return {'success': False, 'error': 'Não autorizado - Verifique API Key'}
                elif response.status_code == 404:
                    return {'success': False, 'error': 'Endpoint não encontrado'}
                elif response.status_code == 429:
                    return {'success': False, 'error': 'Muitas requisições - Tente mais tarde'}
                else:
                    error_msg = f"Erro HTTP {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', error_msg)
                    except:
                        error_msg = response.text or error_msg
                    
                    if attempt < retries:
                        logger.warning(f"Tentativa {attempt + 1} falhou: {error_msg}. Tentando novamente em {self.retry_delay}s...")
                        time.sleep(self.retry_delay)
                        continue
                    
                    return {'success': False, 'error': error_msg}
                    
            except requests.exceptions.ConnectionError:
                error_msg = "Erro de conexão com Baileys API"
                if attempt < retries:
                    logger.warning(f"Tentativa {attempt + 1} falhou: {error_msg}. Tentando novamente em {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': error_msg}
                
            except requests.exceptions.Timeout:
                error_msg = "Timeout na requisição para Baileys API"
                if attempt < retries:
                    logger.warning(f"Tentativa {attempt + 1} falhou: {error_msg}. Tentando novamente em {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': error_msg}
                
            except Exception as e:
                error_msg = f"Erro inesperado: {str(e)}"
                if attempt < retries:
                    logger.warning(f"Tentativa {attempt + 1} falhou: {error_msg}. Tentando novamente em {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': error_msg}
        
        return {'success': False, 'error': 'Máximo de tentativas excedido'}
    
    def get_status(self, chat_id_usuario: int = None) -> Dict:
        """Obtém status da conexão WhatsApp para usuário específico"""
        try:
            # Determinar sessão do usuário
            session_name = self.get_user_session(chat_id_usuario) if chat_id_usuario else self.default_session
            
            # Verificar cache
            now = time.time()
            cache_key = f'status_{session_name}'
            if (cache_key in self._status_cache and 
                now - self._status_cache.get(f'{cache_key}_timestamp', 0) < self._cache_timeout):
                return self._status_cache[cache_key]
            
            # Buscar status atual
            response = self._make_request(f'status/{session_name}')
            
            if response.get('success'):
                status_data = response.get('data', {})
                
                # Processar status
                status = {
                    'status': self._format_connection_status(status_data.get('state', 'disconnected')),
                    'numero': status_data.get('user', {}).get('id', '').replace('@s.whatsapp.net', ''),
                    'bateria': status_data.get('battery', {}).get('percentage'),
                    'ultima_conexao': self._format_last_seen(status_data.get('lastSeen')),
                    'qr_needed': status_data.get('qr') is not None,
                    'mensagens_enviadas': status_data.get('stats', {}).get('sent', 0),
                    'mensagens_falharam': status_data.get('stats', {}).get('failed', 0),
                    'fila_pendente': status_data.get('stats', {}).get('pending', 0)
                }
                
                # Atualizar cache
                self._status_cache[cache_key] = status
                self._status_cache[f'{cache_key}_timestamp'] = now
                
                return status
            else:
                return {
                    'status': '🔴 Erro na conexão',
                    'numero': 'N/A',
                    'bateria': None,
                    'ultima_conexao': 'N/A',
                    'qr_needed': True,
                    'mensagens_enviadas': 0,
                    'mensagens_falharam': 0,
                    'fila_pendente': 0,
                    'error': response.get('error', 'Erro desconhecido')
                }
                
        except Exception as e:
            logger.error(f"Erro ao obter status: {e}")
            return {
                'status': '❌ Erro interno',
                'numero': 'N/A',
                'bateria': None,
                'ultima_conexao': 'N/A',
                'qr_needed': True,
                'mensagens_enviadas': 0,
                'mensagens_falharam': 0,
                'fila_pendente': 0,
                'error': str(e)
            }
    
    def _format_connection_status(self, state: str) -> str:
        """Formata status de conexão"""
        status_map = {
            'open': '🟢 Conectado',
            'connecting': '🟡 Conectando',
            'close': '🔴 Desconectado',
            'disconnected': '🔴 Desconectado'
        }
        return status_map.get(state, f'❓ {state}')
    
    def _format_last_seen(self, timestamp) -> str:
        """Formata última conexão"""
        if not timestamp:
            return 'Nunca'
        
        try:
            if isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(timestamp)
            else:
                dt = datetime.fromisoformat(str(timestamp))
            
            return formatar_datetime_br(dt)
        except:
            return 'Inválido'
    
    def qr_code_needed(self, chat_id_usuario: int) -> bool:
        """Verifica se QR Code é necessário para usuário específico"""
        status = self.get_status(chat_id_usuario)
        return status.get('qr_needed', True)
    
    def generate_qr_code(self, chat_id_usuario: int) -> Dict:
        """Gera QR Code para conexão específica do usuário"""
        try:
            # Determinar sessão do usuário
            session_name = self.get_user_session(chat_id_usuario)
            
            # Primeiro, tentar obter QR code diretamente
            response = self._make_request(f'qr/{session_name}')
            
            if response.get('success'):
                qr_data = response.get('qr')
                qr_image = response.get('qr_image')
                if qr_data:
                    return {
                        'success': True,
                        'qr_code': qr_data,
                        'qr_image': qr_image,
                        'session_id': session_name,
                        'message': 'QR Code gerado com sucesso'
                    }
            
            # Se não há QR disponível, tentar reconectar
            logger.info(f"QR não disponível para {session_name}, tentando reconectar...")
            reconnect_response = self._make_request(f'reconnect/{session_name}', method='POST')
            
            if reconnect_response.get('success'):
                # Aguardar um momento e tentar novamente
                time.sleep(2)
                response = self._make_request(f'qr/{session_name}')
                
                if response.get('success'):
                    qr_data = response.get('qr')
                    qr_image = response.get('qr_image')
                    if qr_data:
                        return {
                            'success': True,
                            'qr_code': qr_data,
                            'qr_image': qr_image,
                            'session_id': session_name,
                            'message': 'QR Code gerado após reconexão'
                        }
            
            return {
                'success': False,
                'error': f'QR Code não disponível para sessão {session_name}',
                'session_id': session_name,
                'suggestion': 'Tente novamente em alguns segundos'
            }
            
        except Exception as e:
            logger.error(f"Erro ao gerar QR Code: {e}")
            return {'success': False, 'error': str(e)}
    
    def clear_session_and_regenerate_qr(self, chat_id_usuario: int) -> Dict:
        """Limpa sessão e força regeneração do QR Code"""
        try:
            session_name = self.get_user_session(chat_id_usuario)
            
            # Limpar sessão existente
            clear_response = self._make_request(f'clear-session/{session_name}', method='POST')
            logger.info(f"Limpeza de sessão {session_name}: {clear_response}")
            
            # Aguardar um momento
            time.sleep(3)
            
            # Tentar reconectar
            reconnect_response = self._make_request(f'reconnect/{session_name}', method='POST')
            logger.info(f"Reconexão {session_name}: {reconnect_response}")
            
            # Aguardar QR ser gerado
            time.sleep(5)
            
            # Buscar QR code
            qr_response = self._make_request(f'qr/{session_name}')
            
            if qr_response.get('success') and qr_response.get('qr'):
                return {
                    'success': True,
                    'qr_code': qr_response.get('qr'),
                    'qr_image': qr_response.get('qr_image'),
                    'session_id': session_name,
                    'message': 'QR Code gerado após limpeza da sessão'
                }
            
            return {
                'success': False,
                'error': 'Não foi possível gerar QR Code após limpeza',
                'session_id': session_name
            }
            
        except Exception as e:
            logger.error(f"Erro ao limpar sessão e gerar QR: {e}")
            return {'success': False, 'error': str(e)}
    
    def request_pairing_code(self, chat_id_usuario: int, phone_number: str) -> Dict:
        """Solicita código de pareamento para conectar WhatsApp"""
        try:
            session_name = self.get_user_session(chat_id_usuario)
            
            # Limpar número de telefone (apenas números)
            import re
            clean_phone = re.sub(r'\D', '', phone_number)
            
            # Se número muito curto, usar número padrão para demonstração
            if len(clean_phone) < 10:
                clean_phone = "5511999999999"  # Número padrão para teste
            
            # Fazer requisição para gerar código de pareamento
            response = self._make_request(f'pairing-code/{session_name}/{clean_phone}')
            
            if response.get('success'):
                return {
                    'success': True,
                    'pairing_code': response.get('pairing_code'),
                    'phone_number': response.get('phone_number'),
                    'session_id': session_name,
                    'message': 'Código de pareamento gerado com sucesso'
                }
            else:
                return {
                    'success': False,
                    'error': response.get('error', 'Erro ao gerar código de pareamento'),
                    'session_id': session_name
                }
                
        except Exception as e:
            logger.error(f"Erro ao solicitar código de pareamento: {e}")
            return {'success': False, 'error': str(e)}
    
    def request_pairing_code_quick(self, chat_id_usuario: int, phone_number: str) -> Dict:
        """Método alternativo rápido para código de pareamento"""
        try:
            session_name = self.get_user_session(chat_id_usuario)
            
            # Limpar número de telefone (apenas números)
            import re
            clean_phone = re.sub(r'\D', '', phone_number)
            
            # Fazer requisição para método alternativo
            response = self._make_request(f'quick-pairing-code/{session_name}/{clean_phone}')
            
            if response.get('success'):
                return {
                    'success': True,
                    'pairing_code': response.get('pairing_code'),
                    'phone_number': response.get('phone_number'),
                    'session_id': session_name,
                    'method': 'quick_generation',
                    'message': 'Código alternativo gerado rapidamente'
                }
            else:
                return {
                    'success': False,
                    'error': response.get('error', 'Erro no método alternativo'),
                    'session_id': session_name
                }
                
        except Exception as e:
            logger.error(f"Erro no método alternativo: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_qr_code_quick(self, chat_id_usuario: int = None) -> Dict:
        """Método rápido para QR Code quando conexão falha"""
        try:
            session_name = self.get_user_session(chat_id_usuario)
            
            # Tentar método rápido
            response = self._make_request(f'qr-quick/{session_name}')
            
            if response.get('success'):
                return {
                    'success': True,
                    'qr_code': response.get('qr'),
                    'qr_image': response.get('qr_image'),
                    'session': session_name,
                    'instructions': response.get('instructions', ''),
                    'method': 'quick',
                    'note': response.get('note', '')
                }
            else:
                return {
                    'success': False,
                    'error': response.get('error', 'QR rápido não disponível')
                }
                
        except Exception as e:
            logger.error(f"Erro no QR rápido: {e}")
            return {'success': False, 'error': str(e)}
            
            # Usar endpoint específico por usuário - sistema multi-sessão
            response = requests.get(f"{self.base_url}/qr/{session_name}", timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return {
                        'success': True,
                        'qr_code': data.get('qr'),
                        'qr_image': data.get('qr_image'),
                        'session': session_name,
                        'instructions': data.get('instructions', '')
                    }
                else:
                    return {
                        'success': False,
                        'error': data.get('error', 'QR Code não disponível')
                    }
            else:
                return {
                    'success': False,
                    'error': f'API retornou status {response.status_code}'
                }
                
        except Exception as e:
            logger.error(f"Erro ao gerar QR Code: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_message(self, phone: str, message: str, chat_id_usuario: int, options: Dict = None) -> Dict:
        """Envia mensagem via WhatsApp do usuário específico"""
        try:
            # Limpar e formatar telefone
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            
            # Preparar dados da mensagem com sessão específica do usuário
            session_name = self.get_user_session(chat_id_usuario)
            data = {
                'number': clean_phone,
                'message': message,
                'session_id': session_name  # Incluir sessionId específico
            }
            
            # Opções adicionais
            if options:
                data.update(options)
            
            # Enviar mensagem via endpoint multi-sessão
            response = requests.post(f"{self.base_url}/send-message", 
                                   json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    # Aguardar delay configurado
                    if self.message_delay > 0:
                        time.sleep(self.message_delay)
                    
                    return {
                        'success': True,
                        'messageId': result.get('messageId'),
                        'status': 'sent',
                        'timestamp': result.get('timestamp', time.time())
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get('error', 'Erro desconhecido')
                    }
            else:
                return {
                    'success': False,
                    'error': f'API retornou status {response.status_code}'
                }
                
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_image(self, phone: str, image_path: str, chat_id_usuario: int, caption: str = None) -> Dict:
        """Envia imagem via WhatsApp do usuário específico"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            
            session_name = self.get_user_session(chat_id_usuario)
            data = {
                'number': clean_phone,
                'image': image_path,
                'session': session_name
            }
            
            if caption:
                data['caption'] = caption
            
            response = self._make_request('send-image', 'POST', data)
            
            if response.get('success'):
                if self.message_delay > 0:
                    time.sleep(self.message_delay)
            
            return response
            
        except Exception as e:
            logger.error(f"Erro ao enviar imagem: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_document(self, phone: str, document_path: str, filename: str = None) -> Dict:
        """Envia documento via WhatsApp"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            
            data = {
                'number': clean_phone,
                'document': document_path,
                'session': self.session_name
            }
            
            if filename:
                data['filename'] = filename
            
            response = self._make_request('send-document', 'POST', data)
            
            if response.get('success'):
                if self.message_delay > 0:
                    time.sleep(self.message_delay)
            
            return response
            
        except Exception as e:
            logger.error(f"Erro ao enviar documento: {e}")
            return {'success': False, 'error': str(e)}
    
    def _clean_phone_number(self, phone: str) -> str:
        """Limpa e formata número de telefone"""
        if not phone:
            return ""
        
        # Remover caracteres não numéricos
        clean = ''.join(filter(str.isdigit, phone))
        
        # Verificar se tem código do país
        if clean.startswith('55'):
            # Brasil: 55 + DDD + número
            if len(clean) >= 12:
                return clean
        else:
            # Adicionar código do Brasil se não tiver
            if len(clean) >= 10:
                return f"55{clean}"
        
        # Verificar se é um número válido (mínimo 10 dígitos)
        if len(clean) >= 10:
            return clean
        
        return ""
    
    def get_chat_info(self, phone: str) -> Dict:
        """Obtém informações do chat"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            
            response = self._make_request(f'chat-info/{self.session_name}/{clean_phone}')
            return response
            
        except Exception as e:
            logger.error(f"Erro ao obter info do chat: {e}")
            return {'success': False, 'error': str(e)}
    
    def is_number_registered(self, phone: str) -> Dict:
        """Verifica se número está registrado no WhatsApp"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            
            data = {
                'number': clean_phone,
                'session': self.session_name
            }
            
            response = self._make_request('check-number', 'POST', data)
            return response
            
        except Exception as e:
            logger.error(f"Erro ao verificar número: {e}")
            return {'success': False, 'error': str(e)}
    
    def reconnect(self) -> Dict:
        """Reconecta a sessão WhatsApp"""
        try:
            response = self._make_request(f'restart/{self.session_name}', 'POST')
            
            # Limpar cache de status
            self._status_cache = {}
            
            return response
            
        except Exception as e:
            logger.error(f"Erro ao reconectar: {e}")
            return {'success': False, 'error': str(e)}
    
    def logout(self) -> Dict:
        """Faz logout da sessão WhatsApp"""
        try:
            response = self._make_request(f'logout/{self.session_name}', 'POST')
            
            # Limpar cache
            self._status_cache = {}
            
            return response
            
        except Exception as e:
            logger.error(f"Erro ao fazer logout: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_config(self) -> Dict:
        """Obtém configurações atuais"""
        return {
            'base_url': self.base_url,
            'session': self.session_name,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'message_delay': self.message_delay,
            'auto_reconnect': self.auto_reconnect,
            'api_key_configured': bool(self.api_key)
        }
    
    def update_config(self, **kwargs) -> bool:
        """Atualiza configurações"""
        try:
            if 'timeout' in kwargs:
                self.timeout = int(kwargs['timeout'])
            
            if 'max_retries' in kwargs:
                self.max_retries = int(kwargs['max_retries'])
            
            if 'message_delay' in kwargs:
                self.message_delay = int(kwargs['message_delay'])
            
            if 'auto_reconnect' in kwargs:
                self.auto_reconnect = bool(kwargs['auto_reconnect'])
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao atualizar configurações: {e}")
            return False
    
    def get_message_history(self, phone: str, limit: int = 50) -> Dict:
        """Obtém histórico de mensagens"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            
            params = {
                'limit': limit
            }
            
            response = self._make_request(f'messages/{self.session_name}/{clean_phone}', 'GET', params)
            return response
            
        except Exception as e:
            logger.error(f"Erro ao obter histórico: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_bulk_messages(self, messages: List[Dict]) -> Dict:
        """Envia múltiplas mensagens em lote"""
        try:
            results = []
            success_count = 0
            error_count = 0
            
            for i, msg_data in enumerate(messages):
                phone = msg_data.get('phone')
                message = msg_data.get('message')
                
                if not phone or not message:
                    results.append({
                        'index': i,
                        'phone': phone,
                        'success': False,
                        'error': 'Dados incompletos'
                    })
                    error_count += 1
                    continue
                
                # Enviar mensagem
                result = self.send_message(phone, message)
                
                results.append({
                    'index': i,
                    'phone': phone,
                    'success': result['success'],
                    'message_id': result.get('message_id'),
                    'error': result.get('error')
                })
                
                if result['success']:
                    success_count += 1
                else:
                    error_count += 1
                
                # Delay entre mensagens
                if i < len(messages) - 1 and self.message_delay > 0:
                    time.sleep(self.message_delay)
            
            return {
                'success': True,
                'total': len(messages),
                'success_count': success_count,
                'error_count': error_count,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Erro no envio em lote: {e}")
            return {'success': False, 'error': str(e)}
    
    def health_check(self) -> Dict:
        """Verifica se a API está funcionando"""
        try:
            response = self._make_request('health', 'GET')
            return response
            
        except Exception as e:
            logger.error(f"Erro no health check: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_sessions(self) -> Dict:
        """Lista todas as sessões ativas"""
        try:
            response = self._make_request('sessions', 'GET')
            return response
            
        except Exception as e:
            logger.error(f"Erro ao obter sessões: {e}")
            return {'success': False, 'error': str(e)}
    
    def registrar_log_envio(self, cliente_id: int, template_id: int = None, telefone: str = "", 
                           mensagem: str = "", tipo_envio: str = "manual", sucesso: bool = False, 
                           message_id: str = None, erro: str = None):
        """Registra log de envio no banco (método de compatibilidade)"""
        try:
            # Este método é chamado pelo bot mas a classe BaileysAPI não tem acesso direto ao DB
            # O registro será feito pelo caller que tem acesso ao DatabaseManager
            logger.info(f"Log de envio: cliente_id={cliente_id}, telefone={telefone}, sucesso={sucesso}")
            
            if not sucesso and erro:
                logger.warning(f"Falha no envio para {telefone}: {erro}")
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao registrar log de envio: {e}")
            return False
