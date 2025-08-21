#!/usr/bin/env python3
"""
Integração com Mercado Pago para cobranças automáticas
Gera QR codes e processa pagamentos
"""
import os
import logging
import requests
import json
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

class MercadoPagoIntegration:
    """Integração com API do Mercado Pago"""
    
    def __init__(self):
        self.access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
        self.base_url = 'https://api.mercadopago.com'
        self.timezone_br = pytz.timezone('America/Sao_Paulo')
        
        if not self.access_token:
            logger.warning("Token do Mercado Pago não configurado")
    
    def criar_cobranca(self, chat_id, valor, descricao, email_usuario=None):
        """Cria cobrança PIX no Mercado Pago"""
        try:
            if not self.access_token:
                return {'success': False, 'message': 'Mercado Pago não configurado'}
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Dados da cobrança
            agora = datetime.now(self.timezone_br)
            expiracao = agora.replace(hour=23, minute=59, second=59)  # Expira no final do dia
            
            # Formato correto para o Mercado Pago: yyyy-MM-dd'T'HH:mm:ssz
            expiracao_formatada = expiracao.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + expiracao.strftime('%z')
            
            data = {
                'transaction_amount': float(valor),
                'description': descricao,
                'payment_method_id': 'pix',
                'external_reference': f'user_{chat_id}_{int(agora.timestamp())}',
                'date_of_expiration': expiracao_formatada,
                'payer': {
                    'email': email_usuario or f'user{chat_id}@sistema.com',
                    'identification': {
                        'type': 'CPF',
                        'number': '11111111111'  # CPF genérico para teste
                    }
                }
            }
            
            # Adicionar email se fornecido
            if email_usuario:
                data['payer']['email'] = email_usuario
            
            response = requests.post(
                f'{self.base_url}/v1/payments',
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 201:
                payment_data = response.json()
                
                return {
                    'success': True,
                    'payment_id': payment_data['id'],
                    'qr_code': payment_data.get('point_of_interaction', {}).get('transaction_data', {}).get('qr_code'),
                    'qr_code_base64': payment_data.get('point_of_interaction', {}).get('transaction_data', {}).get('qr_code_base64'),
                    'ticket_url': payment_data.get('point_of_interaction', {}).get('transaction_data', {}).get('ticket_url'),
                    'external_reference': data['external_reference'],
                    'expiracao': expiracao,
                    'valor': valor
                }
            else:
                logger.error(f"Erro ao criar cobrança MP: {response.status_code} - {response.text}")
                return {
                    'success': False, 
                    'message': f'Erro na API do Mercado Pago: {response.status_code}'
                }
                
        except Exception as e:
            logger.error(f"Erro ao criar cobrança: {e}")
            return {'success': False, 'message': 'Erro interno ao criar cobrança'}
    
    def verificar_status_pagamento(self, payment_id):
        """Verifica status de um pagamento específico"""
        try:
            if not self.access_token:
                return {'success': False, 'message': 'Mercado Pago não configurado'}
            
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            response = requests.get(
                f'{self.base_url}/v1/payments/{payment_id}',
                headers=headers,
                timeout=15
            )
            
            if response.status_code == 200:
                payment_data = response.json()
                
                return {
                    'success': True,
                    'status': payment_data['status'],
                    'status_detail': payment_data.get('status_detail'),
                    'transaction_amount': payment_data.get('transaction_amount'),
                    'external_reference': payment_data.get('external_reference'),
                    'date_approved': payment_data.get('date_approved'),
                    'payment_method': payment_data.get('payment_method_id')
                }
            else:
                logger.error(f"Erro ao verificar pagamento: {response.status_code}")
                return {'success': False, 'message': 'Erro ao verificar pagamento'}
                
        except Exception as e:
            logger.error(f"Erro ao verificar status: {e}")
            return {'success': False, 'message': 'Erro interno'}
    
    def processar_webhook(self, data):
        """Processa webhook do Mercado Pago"""
        try:
            # Extrair informações do webhook
            payment_id = data.get('data', {}).get('id')
            action = data.get('action')
            
            if not payment_id or action != 'payment.updated':
                return {'success': False, 'message': 'Webhook inválido'}
            
            # Verificar status do pagamento
            status_result = self.verificar_status_pagamento(payment_id)
            
            if status_result['success']:
                return {
                    'success': True,
                    'payment_status': status_result['status'],
                    'payment_id': payment_id,
                    'external_reference': status_result.get('external_reference'),
                    'amount': status_result.get('transaction_amount'),
                    'date_approved': status_result.get('date_approved')
                }
            else:
                return status_result
                
        except Exception as e:
            logger.error(f"Erro ao processar webhook: {e}")
            return {'success': False, 'message': 'Erro interno no webhook'}
    
    def verificar_pagamento(self, payment_id):
        """Alias para verificar_status_pagamento - compatibilidade"""
        return self.verificar_status_pagamento(payment_id)
    
    def listar_pagamentos_pendentes(self, external_reference=None):
        """Lista pagamentos pendentes ou por referência"""
        try:
            if not self.access_token:
                return {'success': False, 'message': 'Mercado Pago não configurado'}
            
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            # Parâmetros para buscar pagamentos
            params = {
                'status': 'pending',
                'limit': 50
            }
            
            if external_reference:
                params['external_reference'] = external_reference
            
            response = requests.get(
                f'{self.base_url}/v1/payments/search',
                headers=headers,
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'payments': data.get('results', []),
                    'total': data.get('paging', {}).get('total', 0)
                }
            else:
                logger.error(f"Erro ao listar pagamentos: {response.status_code}")
                return {'success': False, 'message': 'Erro ao buscar pagamentos'}
                
        except Exception as e:
            logger.error(f"Erro ao listar pagamentos: {e}")
            return {'success': False, 'message': 'Erro interno'}
            
        except Exception as e:
            logger.error(f"Erro ao processar webhook: {e}")
            return {'success': False, 'message': 'Erro interno'}
    
    def gerar_qr_code_pix(self, valor, descricao, referencia):
        """Gera QR Code PIX específico"""
        try:
            if not self.access_token:
                return {'success': False, 'message': 'Token não configurado'}
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Criar cobrança PIX
            agora = datetime.now(self.timezone_br)
            expiracao = agora + timedelta(hours=24)  # 24 horas para expirar
            
            data = {
                'transaction_amount': float(valor),
                'description': descricao,
                'payment_method_id': 'pix',
                'external_reference': referencia,
                'date_of_expiration': expiracao.isoformat()
            }
            
            response = requests.post(
                f'{self.base_url}/v1/payments',
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 201:
                result = response.json()
                pix_data = result.get('point_of_interaction', {}).get('transaction_data', {})
                
                return {
                    'success': True,
                    'qr_code': pix_data.get('qr_code'),
                    'qr_code_base64': pix_data.get('qr_code_base64'),
                    'payment_id': result['id'],
                    'ticket_url': pix_data.get('ticket_url')
                }
            else:
                logger.error(f"Erro ao gerar QR PIX: {response.text}")
                return {'success': False, 'message': 'Erro ao gerar QR Code'}
                
        except Exception as e:
            logger.error(f"Erro no QR Code PIX: {e}")
            return {'success': False, 'message': 'Erro interno'}
    
    def is_configured(self):
        """Verifica se a integração está configurada"""
        return bool(self.access_token)
    
    def get_payment_link(self, valor, descricao, external_reference):
        """Gera link de pagamento do Mercado Pago"""
        try:
            if not self.access_token:
                return None
                
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'items': [{
                    'title': descricao,
                    'quantity': 1,
                    'unit_price': float(valor)
                }],
                'external_reference': external_reference,
                'auto_return': 'approved',
                'back_urls': {
                    'success': 'https://seu-dominio.com/success',
                    'failure': 'https://seu-dominio.com/failure',
                    'pending': 'https://seu-dominio.com/pending'
                }
            }
            
            response = requests.post(
                f'{self.base_url}/checkout/preferences',
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 201:
                result = response.json()
                return result.get('init_point')
            
            return None
            
        except Exception as e:
            logger.error(f"Erro ao gerar link de pagamento: {e}")
            return None