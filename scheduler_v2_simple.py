"""
Sistema de Agendamento SUPER SIMPLIFICADO
Versão final simplificada focada apenas no essencial
"""

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from utils import agora_br
import pytz
import requests
import os

logger = logging.getLogger(__name__)

class SimpleScheduler:
    def __init__(self, database_manager, baileys_api, template_manager):
        """Inicializa agendador super simplificado"""
        self.db = database_manager
        self.baileys_api = baileys_api
        self.template_manager = template_manager
        self.bot_instance = None
        
        self.scheduler = BackgroundScheduler(timezone=pytz.timezone('America/Sao_Paulo'))
        self.running = False
        
    def start(self):
        """Inicia o agendador com horários personalizados por usuário"""
        try:
            if not self.running:
                # Configurar jobs personalizados para cada usuário
                self._configurar_jobs_personalizados()
                
                self.scheduler.start()
                self.running = True
                logger.info(f"✅ Agendador iniciado com horários personalizados")
                
        except Exception as e:
            logger.error(f"Erro ao iniciar agendador: {e}")
    
    def stop(self):
        """Para o agendador"""
        try:
            if self.running:
                self.scheduler.shutdown()
                self.running = False
                logger.info("Agendador parado")
        except Exception as e:
            logger.error(f"Erro ao parar agendador: {e}")
    
    def _configurar_jobs_personalizados(self):
        """Configura jobs personalizados para cada usuário"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Buscar todos os usuários com horários personalizados
                    cursor.execute("""
                        SELECT DISTINCT chat_id_usuario 
                        FROM configuracoes 
                        WHERE chat_id_usuario IS NOT NULL 
                        AND chave IN ('horario_verificacao_diaria', 'horario_envio_diario')
                    """)
                    usuarios = cursor.fetchall()
                    
                    for usuario in usuarios:
                        chat_id = usuario[0]
                        self._configurar_jobs_usuario(chat_id)
                        
        except Exception as e:
            logger.error(f"Erro ao configurar jobs personalizados: {e}")
            # Fallback para job global padrão
            self._configurar_job_global()
    
    def _configurar_jobs_usuario(self, chat_id):
        """Configura jobs específicos para um usuário"""
        try:
            # Buscar horários personalizados do usuário
            horario_verificacao = "09:00"
            horario_envio = "09:05"
            
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT chave, valor FROM configuracoes 
                        WHERE chat_id_usuario = %s 
                        AND chave IN ('horario_verificacao_diaria', 'horario_envio_diario')
                    """, (chat_id,))
                    
                    configs = cursor.fetchall()
                    for config in configs:
                        if config[0] == 'horario_verificacao_diaria':
                            horario_verificacao = config[1]
                        elif config[0] == 'horario_envio_diario':
                            horario_envio = config[1]
            
            # Job de verificação para este usuário
            hora_verif, min_verif = map(int, horario_verificacao.split(':'))
            self.scheduler.add_job(
                func=lambda: self._verificar_usuario_especifico(chat_id),
                trigger=CronTrigger(hour=hora_verif, minute=min_verif),
                id=f'verificacao_usuario_{chat_id}',
                name=f'Verificação {chat_id} - {horario_verificacao}',
                replace_existing=True
            )
            
            # Job de envio para este usuário
            hora_envio, min_envio = map(int, horario_envio.split(':'))
            self.scheduler.add_job(
                func=lambda: self._processar_envios_usuario(chat_id),
                trigger=CronTrigger(hour=hora_envio, minute=min_envio),
                id=f'envio_usuario_{chat_id}',
                name=f'Envio {chat_id} - {horario_envio}',
                replace_existing=True
            )
            
            logger.info(f"✅ Jobs configurados para usuário {chat_id}: Verif {horario_verificacao}, Envio {horario_envio}")
            
        except Exception as e:
            logger.error(f"Erro ao configurar jobs para usuário {chat_id}: {e}")
    
    def _configurar_job_global(self):
        """Configura job global padrão como fallback"""
        try:
            self.scheduler.add_job(
                func=self._notificar_usuarios_diario,
                trigger=CronTrigger(hour=9, minute=5),
                id='notificar_usuarios_global',
                name='Notificações Diárias Global 09:05',
                replace_existing=True
            )
            logger.info("✅ Job global configurado como fallback")
        except Exception as e:
            logger.error(f"Erro ao configurar job global: {e}")
    
    def _verificar_usuario_especifico(self, chat_id):
        """Verifica vencimentos para um usuário específico"""
        try:
            logger.info(f"🔍 Verificando vencimentos para usuário {chat_id}")
            
            # Buscar clientes vencidos há exatamente 1 dia
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, nome, telefone, vencimento, valor 
                        FROM clientes 
                        WHERE chat_id_usuario = %s
                        AND vencimento = CURRENT_DATE - INTERVAL '1 day'
                        AND receber_cobranca = true
                        AND ativo = true
                    """, (chat_id,))
                    
                    clientes_vencidos = cursor.fetchall()
                    
                    if clientes_vencidos:
                        logger.info(f"📋 {len(clientes_vencidos)} cliente(s) vencido(s) há 1 dia para usuário {chat_id}")
                        
                        # Adicionar à fila de mensagens
                        for cliente in clientes_vencidos:
                            self._adicionar_mensagem_fila(chat_id, cliente)
                    else:
                        logger.info(f"✅ Nenhum cliente vencido há 1 dia para usuário {chat_id}")
                        
        except Exception as e:
            logger.error(f"Erro ao verificar usuário {chat_id}: {e}")
    
    def _processar_envios_usuario(self, chat_id):
        """Processa envios de mensagens para um usuário específico"""
        try:
            logger.info(f"📤 Processando envios para usuário {chat_id}")
            
            # Buscar mensagens pendentes na fila
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, cliente_id, template_id, variaveis, telefone_destino
                        FROM fila_mensagens 
                        WHERE chat_id_usuario = %s
                        AND status = 'pendente'
                        AND data_agendamento <= CURRENT_DATE
                    """, (chat_id,))
                    
                    mensagens = cursor.fetchall()
                    
                    if mensagens:
                        logger.info(f"📨 {len(mensagens)} mensagem(ns) para enviar para usuário {chat_id}")
                        
                        for mensagem in mensagens:
                            self._enviar_mensagem_fila(mensagem, chat_id)
                    else:
                        logger.info(f"✅ Nenhuma mensagem pendente para usuário {chat_id}")
                        
        except Exception as e:
            logger.error(f"Erro ao processar envios para usuário {chat_id}: {e}")
    
    def _adicionar_mensagem_fila(self, chat_id, cliente):
        """Adiciona mensagem de cobrança à fila"""
        try:
            cliente_id, nome, telefone, vencimento, valor = cliente
            
            # Buscar template de cobrança do usuário
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id FROM templates 
                        WHERE chat_id_usuario = %s 
                        AND tipo = 'cobranca'
                        AND ativo = true
                        ORDER BY id DESC LIMIT 1
                    """, (chat_id,))
                    
                    template = cursor.fetchone()
                    if not template:
                        logger.warning(f"⚠️ Nenhum template de cobrança encontrado para usuário {chat_id}")
                        return
                    
                    template_id = template[0]
                    
                    # Inserir na fila
                    cursor.execute("""
                        INSERT INTO fila_mensagens 
                        (chat_id_usuario, cliente_id, template_id, telefone_destino, 
                         variaveis, data_agendamento, status) 
                        VALUES (%s, %s, %s, %s, %s, CURRENT_DATE, 'pendente')
                    """, (chat_id, cliente_id, template_id, telefone, 
                          f'{{"nome": "{nome}", "valor": "{valor}", "vencimento": "{vencimento}"}}'))
                    
                    logger.info(f"✅ Mensagem adicionada à fila: {nome} ({telefone})")
                    
        except Exception as e:
            logger.error(f"Erro ao adicionar mensagem à fila: {e}")
    
    def _enviar_mensagem_fila(self, mensagem_data, chat_id):
        """Envia mensagem da fila via WhatsApp"""
        try:
            fila_id, cliente_id, template_id, variaveis, telefone = mensagem_data
            
            # Buscar template
            template_content = self.template_manager.buscar_template_por_id(template_id)
            if not template_content:
                logger.error(f"❌ Template {template_id} não encontrado")
                return
            
            # Processar variáveis
            import json
            vars_dict = json.loads(variaveis) if variaveis else {}
            
            # Substituir variáveis no template
            mensagem_final = template_content
            for var, valor in vars_dict.items():
                mensagem_final = mensagem_final.replace(f'{{{var}}}', str(valor))
            
            # Enviar via Baileys
            result = self.baileys_api.send_message(
                phone_number=telefone,
                message=mensagem_final,
                session_id=f"user_{chat_id}"
            )
            
            # Atualizar status na fila
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    if result.get('success'):
                        cursor.execute("""
                            UPDATE fila_mensagens 
                            SET status = 'enviada', data_envio = NOW()
                            WHERE id = %s
                        """, (fila_id,))
                        logger.info(f"✅ Mensagem enviada com sucesso: {telefone}")
                    else:
                        cursor.execute("""
                            UPDATE fila_mensagens 
                            SET status = 'erro', observacoes = %s
                            WHERE id = %s
                        """, (result.get('error', 'Erro desconhecido'), fila_id))
                        logger.error(f"❌ Erro ao enviar mensagem: {telefone}")
                        
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem da fila: {e}")
    
    def _buscar_horario_verificacao_legacy(self):
        """Método legacy mantido para compatibilidade"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT valor FROM configuracoes 
                        WHERE chave = 'horario_verificacao_diaria' 
                        AND chat_id_usuario IS NULL
                        ORDER BY id DESC LIMIT 1
                    """)
                    resultado = cursor.fetchone()
                    
                    if resultado:
                        return resultado[0]
                    else:
                        return "09:05"  # Padrão
        except Exception as e:
            logger.error(f"Erro ao buscar horário: {e}")
            return "09:05"  # Padrão em caso de erro
    
    def recriar_jobs(self, novo_horario_verificacao=None):
        """Recria os jobs com novos horários"""
        try:
            # Parar scheduler atual
            if self.running:
                self.scheduler.shutdown()
                self.running = False
                logger.info("Scheduler parado para recriar jobs")
            
            # Criar novo scheduler
            self.scheduler = BackgroundScheduler(timezone=pytz.timezone('America/Sao_Paulo'))
            
            # Buscar horário (usar novo se fornecido)
            if novo_horario_verificacao:
                horario = novo_horario_verificacao
            else:
                horario = self._buscar_horario_verificacao()
                
            hora, minuto = map(int, horario.split(':'))
            
            # Recriar job
            self.scheduler.add_job(
                func=self._notificar_usuarios_diario,
                trigger=CronTrigger(hour=hora, minute=minuto),
                id='notificar_usuarios',
                name=f'Notificações Diárias {horario}',
                replace_existing=True
            )
            
            # Reiniciar
            self.scheduler.start()
            self.running = True
            logger.info(f"✅ Jobs recriados: Notificações {horario}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao recriar jobs: {e}")
            return False
    
    def _notificar_usuarios_diario(self):
        """Notifica cada usuário sobre seus clientes vencendo"""
        try:
            logger.info("=== NOTIFICAÇÕES DIÁRIAS INICIADAS ===")
            hoje = agora_br().date()
            
            # Buscar todos os usuários do sistema
            usuarios = self._buscar_usuarios_sistema()
            logger.info(f"Encontrados {len(usuarios)} usuários para notificar")
            
            for usuario in usuarios:
                try:
                    chat_id = usuario['chat_id']
                    self._enviar_notificacao_usuario(chat_id, hoje)
                except Exception as e:
                    logger.error(f"Erro ao notificar usuário {usuario.get('chat_id', 'desconhecido')}: {e}")
            
            logger.info("=== NOTIFICAÇÕES CONCLUÍDAS ===")
            
        except Exception as e:
            logger.error(f"Erro nas notificações diárias: {e}")
    
    def _buscar_usuarios_sistema(self):
        """Busca usuários ativos do sistema"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT chat_id 
                        FROM usuarios 
                        WHERE status IN ('ativo', 'teste')
                    """)
                    resultados = cursor.fetchall()
                    return [{'chat_id': row[0]} for row in resultados]
        except Exception as e:
            logger.error(f"Erro ao buscar usuários: {e}")
            return []
    
    def _enviar_notificacao_usuario(self, chat_id_usuario, hoje):
        """Envia notificação individual para um usuário"""
        try:
            logger.info(f"Enviando notificação para usuário {chat_id_usuario}")
            
            # Buscar clientes APENAS deste usuário
            clientes = self.db.listar_clientes(apenas_ativos=True, chat_id_usuario=chat_id_usuario)
            
            if not clientes:
                logger.info(f"Usuário {chat_id_usuario} não tem clientes ativos")
                return
            
            # Categorizar clientes
            vencidos = []
            vence_hoje = []
            vence_proximos = []
            
            for cliente in clientes:
                vencimento = cliente['vencimento']
                dias_diferenca = (vencimento - hoje).days
                
                if dias_diferenca < 0:
                    vencidos.append(cliente)
                elif dias_diferenca == 0:
                    vence_hoje.append(cliente)
                elif 1 <= dias_diferenca <= 7:
                    vence_proximos.append(cliente)
            
            # Criar mensagem apenas se houver algo importante
            if vencidos or vence_hoje or vence_proximos:
                mensagem = f"🚨 *ALERTA DIÁRIO - {hoje.strftime('%d/%m/%Y')}*\n\n"
                
                if vencidos:
                    mensagem += f"🔴 *VENCIDOS ({len(vencidos)}):*\n"
                    for cliente in vencidos[:3]:
                        dias_vencido = abs((cliente['vencimento'] - hoje).days)
                        mensagem += f"• {cliente['nome']} - há {dias_vencido} dia(s)\n"
                    if len(vencidos) > 3:
                        mensagem += f"• +{len(vencidos) - 3} outros\n"
                    mensagem += "\n"
                
                if vence_hoje:
                    mensagem += f"⚠️ *VENCEM HOJE ({len(vence_hoje)}):*\n"
                    for cliente in vence_hoje:
                        mensagem += f"• {cliente['nome']} - R$ {cliente['valor']:.2f}\n"
                    mensagem += "\n"
                
                if vence_proximos:
                    mensagem += f"📅 *PRÓXIMOS 7 DIAS ({len(vence_proximos)}):*\n"
                    for cliente in vence_proximos[:3]:
                        dias_restantes = (cliente['vencimento'] - hoje).days
                        mensagem += f"• {cliente['nome']} - {dias_restantes} dia(s)\n"
                    if len(vence_proximos) > 3:
                        mensagem += f"• +{len(vence_proximos) - 3} outros\n"
                
                mensagem += f"\n📊 Total de clientes: {len(clientes)}\n"
                mensagem += "💡 Use /vencimentos para detalhes"
                
                # Enviar para o usuário
                sucesso = self._enviar_telegram(chat_id_usuario, mensagem)
                if sucesso:
                    logger.info(f"📱 Notificação enviada com sucesso para usuário {chat_id_usuario}")
                else:
                    logger.error(f"Falha ao enviar notificação para usuário {chat_id_usuario}")
            else:
                logger.info(f"Usuário {chat_id_usuario} não tem vencimentos próximos")
            
        except Exception as e:
            logger.error(f"Erro ao notificar usuário {chat_id_usuario}: {e}")
    
    def _enviar_telegram(self, chat_id, mensagem):
        """Envia mensagem via Telegram"""
        try:
            bot_token = os.getenv('BOT_TOKEN')
            if not bot_token:
                logger.error("BOT_TOKEN não configurado")
                return False
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': mensagem,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Erro Telegram: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar Telegram: {e}")
            return False
    
    def is_running(self):
        """Verifica se agendador está rodando"""
        return self.running and self.scheduler.running if self.scheduler else False
    
    def set_bot_instance(self, bot_instance):
        """Define instância do bot (compatibilidade)"""
        self.bot_instance = bot_instance
        logger.info("Bot instance configurada no agendador simplificado")
    
    def reagendar_manual(self):
        """Execução manual para teste"""
        try:
            logger.info("🔄 EXECUÇÃO MANUAL DE TESTE")
            self._notificar_usuarios_diario()
            logger.info("✅ EXECUÇÃO MANUAL CONCLUÍDA")
        except Exception as e:
            logger.error(f"Erro na execução manual: {e}")
    
    def processar_todos_vencidos(self, forcar_reprocesso=False):
        """Compatibilidade: processa todos os vencidos"""
        try:
            logger.info("🔄 Processamento de todos os vencidos solicitado")
            # No sistema simplificado, apenas notificamos os usuários
            self._notificar_usuarios_diario()
            logger.info("✅ Processamento concluído")
            return 0
        except Exception as e:
            logger.error(f"Erro no processamento: {e}")
            return 0
    
    def _setup_main_jobs(self):
        """Compatibilidade: recria jobs principais"""
        try:
            logger.info("🔄 Recriando jobs do agendador...")
            
            # Remove jobs existentes
            for job in list(self.scheduler.get_jobs()):
                job.remove()
            
            # Recria job de notificações
            self.scheduler.add_job(
                func=self._notificar_usuarios_diario,
                trigger=CronTrigger(hour=9, minute=5),
                id='notificar_usuarios',
                name='Notificações Diárias 9h05',
                replace_existing=True
            )
            
            logger.info("✅ Jobs recriados com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao recriar jobs: {e}")
            return False
    
    def get_jobs(self):
        """Compatibilidade: retorna lista de jobs"""
        try:
            return self.scheduler.get_jobs() if self.scheduler else []
        except Exception as e:
            logger.error(f"Erro ao obter jobs: {e}")
            return []