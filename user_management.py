#!/usr/bin/env python3
"""
Sistema de Gerenciamento de Usuários
Controla cadastro, período de teste, pagamentos e acesso ao sistema
"""
import os
import logging
from datetime import datetime, timedelta
import pytz
from database import DatabaseManager

logger = logging.getLogger(__name__)

class UserManager:
    """Gerencia usuários, teste gratuito e controle de acesso"""
    
    def __init__(self, db):
        self.db = db
        self.timezone_br = pytz.timezone('America/Sao_Paulo')
        self.valor_mensal = 20.00
        self.dias_teste_gratuito = 7
        
    def cadastrar_usuario(self, chat_id, nome, email, telefone):
        """Cadastra novo usuário com período de teste gratuito"""
        try:
            # Verificar se usuário já existe
            if self.verificar_usuario_existe(chat_id):
                return {'success': False, 'message': 'Usuário já cadastrado no sistema'}
            
            agora = datetime.now(self.timezone_br)
            fim_teste = agora + timedelta(days=self.dias_teste_gratuito)
            
            # Inserir usuário
            query = """
            INSERT INTO usuarios (
                chat_id, nome, email, telefone, 
                data_cadastro, fim_periodo_teste, status, plano_ativo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db.execute_query(query, [
                chat_id, nome, email, telefone,
                agora, fim_teste, 'teste_gratuito', True
            ])
            
            logger.info(f"Usuário cadastrado: {nome} (chat_id: {chat_id})")
            
            return {
                'success': True, 
                'message': f'Cadastro realizado com sucesso! Você tem {self.dias_teste_gratuito} dias de teste gratuito.',
                'fim_teste': fim_teste
            }
            
        except Exception as e:
            logger.error(f"Erro ao cadastrar usuário: {e}")
            return {'success': False, 'message': 'Erro interno ao realizar cadastro'}
    
    def verificar_usuario_existe(self, chat_id):
        """Verifica se usuário já está cadastrado"""
        try:
            query = "SELECT id FROM usuarios WHERE chat_id = %s"
            result = self.db.fetch_one(query, [chat_id])
            return result is not None
        except Exception as e:
            logger.error(f"Erro ao verificar usuário: {e}")
            return False
    
    def obter_usuario(self, chat_id):
        """Obtém dados completos do usuário"""
        try:
            query = """
            SELECT chat_id, nome, email, telefone, data_cadastro, 
                   fim_periodo_teste, ultimo_pagamento, proximo_vencimento,
                   status, plano_ativo, total_pagamentos
            FROM usuarios WHERE chat_id = %s
            """
            return self.db.fetch_one(query, [chat_id])
        except Exception as e:
            logger.error(f"Erro ao obter usuário: {e}")
            return None
    
    def verificar_acesso(self, chat_id):
        """Verifica se usuário tem acesso ao sistema"""
        try:
            usuario = self.obter_usuario(chat_id)
            if not usuario:
                return {'acesso': False, 'motivo': 'usuario_nao_cadastrado'}
            
            agora = datetime.now(self.timezone_br)
            
            # Verificar se ainda está no período de teste
            if usuario['status'] == 'teste_gratuito':
                fim_periodo_teste = usuario['fim_periodo_teste']
                if fim_periodo_teste.tzinfo is None:
                    fim_periodo_teste = self.timezone_br.localize(fim_periodo_teste)
                
                if agora <= fim_periodo_teste:
                    dias_restantes = (fim_periodo_teste - agora).days
                    return {
                        'acesso': True, 
                        'tipo': 'teste',
                        'dias_restantes': dias_restantes,
                        'usuario': usuario
                    }
                else:
                    # Teste expirado, precisa pagar
                    self.atualizar_status_usuario(chat_id, 'teste_expirado', False)
                    return {'acesso': False, 'motivo': 'teste_expirado', 'usuario': usuario}
            
            # Verificar se tem plano pago ativo
            if usuario['status'] == 'pago' and usuario['plano_ativo']:
                if usuario['proximo_vencimento']:
                    proximo_vencimento = usuario['proximo_vencimento']
                    if proximo_vencimento.tzinfo is None:
                        proximo_vencimento = self.timezone_br.localize(proximo_vencimento)
                    
                    if agora <= proximo_vencimento:
                        dias_restantes = (proximo_vencimento - agora).days
                        return {
                            'acesso': True, 
                            'tipo': 'pago',
                            'dias_restantes': dias_restantes,
                            'usuario': usuario
                        }
                else:
                    # Plano vencido
                    self.atualizar_status_usuario(chat_id, 'vencido', False)
                    return {'acesso': False, 'motivo': 'plano_vencido', 'usuario': usuario}
            
            # Sem acesso
            return {'acesso': False, 'motivo': 'sem_plano_ativo', 'usuario': usuario}
            
        except Exception as e:
            logger.error(f"Erro ao verificar acesso: {e}")
            return {'acesso': False, 'motivo': 'erro_interno'}
    
    def atualizar_status_usuario(self, chat_id, status, plano_ativo):
        """Atualiza status e plano ativo do usuário"""
        try:
            query = "UPDATE usuarios SET status = %s, plano_ativo = %s WHERE chat_id = %s"
            self.db.execute_query(query, [status, plano_ativo, chat_id])
            logger.info(f"Status do usuário {chat_id} atualizado para: {status}")
        except Exception as e:
            logger.error(f"Erro ao atualizar status do usuário: {e}")
    
    def atualizar_dados_usuario(self, chat_id, **kwargs):
        """Atualiza dados pessoais do usuário (nome, email, telefone)"""
        try:
            # Campos permitidos para atualização
            campos_permitidos = ['nome', 'email', 'telefone']
            updates = []
            valores = []
            
            for campo, valor in kwargs.items():
                if campo in campos_permitidos and valor:
                    updates.append(f"{campo} = %s")
                    valores.append(valor)
            
            if not updates:
                return {'success': False, 'message': 'Nenhum campo válido para atualização'}
            
            # Construir query
            query = f"UPDATE usuarios SET {', '.join(updates)} WHERE chat_id = %s"
            valores.append(chat_id)
            
            self.db.execute_query(query, valores)
            
            logger.info(f"Dados do usuário {chat_id} atualizados: {list(kwargs.keys())}")
            
            return {
                'success': True,
                'message': f"Dados atualizados com sucesso: {', '.join(kwargs.keys())}"
            }
            
        except Exception as e:
            logger.error(f"Erro ao atualizar dados do usuário: {e}")
            return {'success': False, 'message': 'Erro interno ao atualizar dados'}
    
    def processar_pagamento(self, chat_id, valor_pago, referencia_pagamento):
        """Processa pagamento aprovado e ativa plano mensal"""
        try:
            agora = datetime.now(self.timezone_br)
            proximo_vencimento = agora + timedelta(days=30)  # 30 dias
            
            # Atualizar dados do usuário
            query = """
            UPDATE usuarios SET 
                status = %s, 
                plano_ativo = %s,
                ultimo_pagamento = %s,
                proximo_vencimento = %s,
                total_pagamentos = COALESCE(total_pagamentos, 0) + %s
            WHERE chat_id = %s
            """
            
            self.db.execute_query(query, [
                'pago', True, agora, proximo_vencimento, valor_pago, chat_id
            ])
            
            # Registrar pagamento
            self.registrar_pagamento(chat_id, valor_pago, referencia_pagamento)
            
            logger.info(f"Pagamento processado para usuário {chat_id}: R$ {valor_pago}")
            
            return {
                'success': True,
                'message': 'Pagamento aprovado! Plano ativado por 30 dias.',
                'proximo_vencimento': proximo_vencimento
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar pagamento: {e}")
            return {'success': False, 'message': 'Erro ao processar pagamento'}
    
    def ativar_plano(self, chat_id, payment_id, valor=20.00):
        """Ativa plano mensal após confirmação de pagamento (alias para processar_pagamento)"""
        try:
            logger.info(f"🔥 Ativando plano para usuário {chat_id} com payment_id {payment_id}")
            resultado = self.processar_pagamento(chat_id, valor, payment_id)
            
            if resultado.get('success'):
                logger.info(f"✅ Plano ativado com sucesso para usuário {chat_id}")
            else:
                logger.error(f"❌ Falha ao ativar plano para usuário {chat_id}: {resultado.get('message')}")
                
            return resultado
        except Exception as e:
            logger.error(f"Erro ao ativar plano: {e}")
            return {'success': False, 'message': 'Erro interno ao ativar plano'}
    
    def registrar_pagamento(self, chat_id, valor, referencia):
        """Registra pagamento no histórico"""
        try:
            agora = datetime.now(self.timezone_br)
            query = """
            INSERT INTO pagamentos (chat_id, valor, data_pagamento, referencia, status)
            VALUES (%s, %s, %s, %s, %s)
            """
            self.db.execute_query(query, [chat_id, valor, agora, referencia, 'aprovado'])
        except Exception as e:
            logger.error(f"Erro ao registrar pagamento: {e}")
    
    def obter_estatisticas_usuario(self, chat_id):
        """Obtém estatísticas do usuário"""
        try:
            usuario = self.obter_usuario(chat_id)
            if not usuario:
                return None
                
            # Contar clientes do usuário
            query_clientes = "SELECT COUNT(*) as total FROM clientes WHERE chat_id_usuario = %s"
            total_clientes = self.db.fetch_one(query_clientes, [chat_id])
            
            # Contar mensagens enviadas
            query_mensagens = "SELECT COUNT(*) as total FROM logs_envio WHERE chat_id_usuario = %s"
            total_mensagens = self.db.fetch_one(query_mensagens, [chat_id])
            
            return {
                'usuario': usuario,
                'total_clientes': total_clientes['total'] if total_clientes else 0,
                'total_mensagens': total_mensagens['total'] if total_mensagens else 0,
                'total_pagamentos': usuario.get('total_pagamentos', 0)
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return None
    
    def listar_usuarios_vencendo(self, dias_aviso=3):
        """Lista usuários que vão vencer em X dias"""
        try:
            limite = datetime.now(self.timezone_br) + timedelta(days=dias_aviso)
            
            query = """
            SELECT chat_id, nome, email, proximo_vencimento
            FROM usuarios 
            WHERE status = 'pago' 
            AND plano_ativo = true 
            AND proximo_vencimento <= %s
            ORDER BY proximo_vencimento ASC
            """
            
            return self.db.fetch_all(query, [limite])
            
        except Exception as e:
            logger.error(f"Erro ao listar usuários vencendo: {e}")
            return []
    
    def get_valor_mensal(self):
        """Retorna valor da mensalidade"""
        return self.valor_mensal
    
    def obter_estatisticas(self):
        """Obtém estatísticas gerais do sistema"""
        try:
            agora = datetime.now(self.timezone_br)
            
            # Estatísticas de usuários
            query_total = "SELECT COUNT(*) as total FROM usuarios"
            total_usuarios = self.db.fetch_one(query_total)
            
            query_ativos = "SELECT COUNT(*) as total FROM usuarios WHERE status = 'pago' AND plano_ativo = true"
            usuarios_ativos = self.db.fetch_one(query_ativos)
            
            query_teste = "SELECT COUNT(*) as total FROM usuarios WHERE status = 'teste_gratuito' AND plano_ativo = true"
            usuarios_teste = self.db.fetch_one(query_teste)
            
            # Faturamento mensal estimado
            query_faturamento = "SELECT SUM(%s) as total FROM usuarios WHERE status = 'pago' AND plano_ativo = true"
            resultado_faturamento = self.db.fetch_one(query_faturamento, [self.valor_mensal])
            
            return {
                'total_usuarios': total_usuarios['total'] if total_usuarios else 0,
                'usuarios_ativos': usuarios_ativos['total'] if usuarios_ativos else 0,
                'usuarios_teste': usuarios_teste['total'] if usuarios_teste else 0,
                'faturamento_mensal': resultado_faturamento['total'] if resultado_faturamento and resultado_faturamento['total'] else 0
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {
                'total_usuarios': 0,
                'usuarios_ativos': 0,
                'usuarios_teste': 0,
                'faturamento_mensal': 0
            }
    
    def obter_estatisticas_faturamento(self):
        """Obtém estatísticas detalhadas de faturamento"""
        try:
            # Faturamento atual
            query_faturamento_atual = """
            SELECT COUNT(*) as usuarios_ativos, SUM(%s) as faturamento_mensal
            FROM usuarios 
            WHERE status = 'pago' AND plano_ativo = true
            """
            resultado_atual = self.db.fetch_one(query_faturamento_atual, [self.valor_mensal])
            
            # Histórico de pagamentos
            query_historico = """
            SELECT 
                COUNT(*) as total_pagamentos,
                SUM(valor) as total_arrecadado,
                DATE_PART('month', data_pagamento) as mes,
                DATE_PART('year', data_pagamento) as ano
            FROM pagamentos 
            WHERE status = 'aprovado'
            GROUP BY DATE_PART('year', data_pagamento), DATE_PART('month', data_pagamento)
            ORDER BY ano DESC, mes DESC
            LIMIT 12
            """
            historico = self.db.fetch_all(query_historico)
            
            # Usuários em teste que podem converter
            query_conversao = """
            SELECT COUNT(*) as usuarios_teste_ativo
            FROM usuarios 
            WHERE status = 'teste_gratuito' AND plano_ativo = true
            """
            conversao = self.db.fetch_one(query_conversao)
            
            usuarios_ativos = resultado_atual['usuarios_ativos'] if resultado_atual else 0
            faturamento_mensal = resultado_atual['faturamento_mensal'] if resultado_atual else 0
            usuarios_teste = conversao['usuarios_teste_ativo'] if conversao else 0
            
            # Projeções
            projecao_conversao = usuarios_teste * self.valor_mensal * 0.3  # 30% de taxa de conversão
            
            return {
                'usuarios_ativos': usuarios_ativos,
                'faturamento_mensal': float(faturamento_mensal) if faturamento_mensal else 0.0,
                'usuarios_teste': usuarios_teste,
                'projecao_conversao': float(projecao_conversao),
                'historico': historico or [],
                'potencial_crescimento': float((usuarios_ativos + usuarios_teste) * self.valor_mensal)
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas de faturamento: {e}")
            return {
                'usuarios_ativos': 0,
                'faturamento_mensal': 0.0,
                'usuarios_teste': 0,
                'projecao_conversao': 0.0,
                'historico': [],
                'potencial_crescimento': 0.0
            }
    
    def listar_todos_usuarios(self, limit=50):
        """Lista todos os usuários do sistema"""
        try:
            query = """
            SELECT 
                chat_id, nome, email, telefone, status, plano_ativo, 
                proximo_vencimento, data_cadastro
            FROM usuarios 
            ORDER BY data_cadastro DESC
            LIMIT %s
            """
            usuarios = self.db.fetch_all(query, [limit])
            return usuarios or []
            
        except Exception as e:
            logger.error(f"Erro ao listar todos os usuários: {e}")
            return []
    
    def listar_usuarios_por_status(self, status):
        """Lista usuários por status específico"""
        try:
            query = """
                SELECT id, chat_id, nome, email, status, proximo_vencimento, data_cadastro
                FROM usuarios 
                WHERE status = %s
                ORDER BY data_cadastro DESC
            """
            usuarios = self.db.fetch_all(query, [status])
            return [dict(u) for u in usuarios] if usuarios else []
                
        except Exception as e:
            logger.error(f"Erro ao listar usuários por status {status}: {e}")
            return []
    
    def obter_transacoes_recentes(self, dias=30):
        """Obtém transações recentes dos últimos N dias"""
        try:
            from datetime import datetime, timedelta
            
            query = """
                SELECT 
                    u.nome as usuario_nome,
                    u.email,
                    p.valor,
                    p.status,
                    p.data_criacao,
                    p.data_pagamento,
                    p.payment_id
                FROM pagamentos p 
                JOIN usuarios u ON p.usuario_id = u.id 
                WHERE p.data_criacao >= %s 
                ORDER BY p.data_criacao DESC 
                LIMIT 100
            """
            
            data_limite = datetime.now() - timedelta(days=dias)
            transacoes = self.db.fetch_all(query, [data_limite])
            
            if not transacoes:
                return []
                
            # Converter para formato mais legível
            resultado = []
            for t in transacoes:
                transacao_dict = dict(t)
                # Formatar datas
                if transacao_dict.get('data_pagamento'):
                    transacao_dict['data_pagamento'] = transacao_dict['data_pagamento'].strftime('%d/%m/%Y %H:%M')
                if transacao_dict.get('data_criacao'):
                    transacao_dict['data_criacao'] = transacao_dict['data_criacao'].strftime('%d/%m/%Y %H:%M')
                
                resultado.append(transacao_dict)
            
            return resultado
                
        except Exception as e:
            logger.error(f"Erro ao obter transações recentes: {e}")
            return []