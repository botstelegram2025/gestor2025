"""
Configurações de Horários do Sistema
Funções para alterar horários de verificação, envio e limpeza via bot
"""

import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class ScheduleConfig:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.timezone = pytz.timezone('America/Sao_Paulo')
        
    def config_horarios_menu(self, chat_id):
        """Menu principal de configuração de horários"""
        try:
            agora = datetime.now(self.timezone)
            
            # Buscar horários personalizados do usuário
            horario_envio = "09:00"
            horario_verificacao = "09:00"
            horario_limpeza = "02:00"
            
            try:
                with self.bot.db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Buscar horários personalizados
                        cursor.execute('''
                            SELECT chave, valor FROM configuracoes 
                            WHERE chat_id_usuario = %s
                            AND chave IN ('horario_envio_diario', 'horario_verificacao_diaria', 'horario_limpeza_fila')
                        ''', (chat_id,))
                        
                        configs = cursor.fetchall()
                        for config in configs:
                            if config[0] == 'horario_envio_diario':
                                horario_envio = config[1]
                            elif config[0] == 'horario_verificacao_diaria':
                                horario_verificacao = config[1]
                            elif config[0] == 'horario_limpeza_fila':
                                horario_limpeza = config[1]
            except:
                pass  # Usar horários padrão se falhar
            
            mensagem = f"""⏰ CONFIGURAÇÕES DE HORÁRIOS

📅 Seus Horários Atuais (Brasília):
🕘 Envio Diário: {horario_envio}
   └ Mensagens são enviadas automaticamente

🕔 Verificação: {horario_verificacao}  
   └ Sistema verifica vencimentos e adiciona à fila

🕚 Limpeza: {horario_limpeza}
   └ Remove mensagens antigas da fila

💡 EXEMPLO DE CONFIGURAÇÃO PERSONALIZADA:
   • Verificação: 18:00 (detecta vencimentos)
   • Envio: 18:10 (envia 10 minutos depois)

🌍 Timezone: America/Sao_Paulo
⏱️ Horário atual: {agora.strftime('%H:%M:%S')}

🔧 Escolha o que deseja alterar:"""

            inline_keyboard = [
                [
                    {'text': '🕘 Horário de Envio', 'callback_data': 'edit_horario_envio'},
                    {'text': '🕔 Horário Verificação', 'callback_data': 'edit_horario_verificacao'}
                ],
                [
                    {'text': '🕚 Horário Limpeza', 'callback_data': 'edit_horario_limpeza'},
                    {'text': '⏱️ Padrões de Envio', 'callback_data': 'edit_padroes_envio'}
                ],
                [
                    {'text': '🔄 Recriar Jobs', 'callback_data': 'recriar_jobs'},
                    {'text': '📊 Status Jobs', 'callback_data': 'status_jobs'}
                ],
                [
                    {'text': '🔄 Reset para Padrão', 'callback_data': 'reset_horarios_padrao'}
                ],
                [
                    {'text': '🔙 Voltar', 'callback_data': 'voltar_configs'},
                    {'text': '🏠 Menu Principal', 'callback_data': 'menu_principal'}
                ]
            ]

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao mostrar menu de horários: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar configurações de horários.")

    def edit_horario_envio(self, chat_id):
        """Configurar horário de envio de mensagens"""
        try:
            # Buscar horário atual do usuário
            horario_atual = "09:00"
            try:
                with self.bot.db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute('''
                            SELECT valor FROM configuracoes 
                            WHERE chat_id_usuario = %s AND chave = 'horario_envio_diario'
                        ''', (chat_id,))
                        resultado = cursor.fetchone()
                        if resultado:
                            horario_atual = resultado[0]
            except:
                pass
                
            mensagem = f"""📤 ALTERAR HORÁRIO DE ENVIO

⏰ Atual: {horario_atual} (Brasília)

Este horário define quando as mensagens da fila são processadas e enviadas via WhatsApp.

💡 Recomendações para configuração sequencial:
   • Se verificação às 18:00 → Envio às 18:10
   • Se verificação às 09:00 → Envio às 09:15
   • Deixe alguns minutos entre verificação e envio

🎯 HORÁRIOS POPULARES:
   • 09:00 (manhã) • 12:00 (almoço) • 18:00 (final tarde)

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            
            # Horários populares incluindo sequências de 18:00-18:10
            horarios_populares = [
                ['09:00', '09:15', '12:00'],
                ['14:00', '16:00', '17:00'], 
                ['17:28', '18:00', '18:10'],
                ['19:00', '20:00', '21:00']
            ]
            
            # Adicionar horários populares
            for linha_horarios in horarios_populares:
                linha = []
                for horario in linha_horarios:
                    linha.append({
                        'text': f'🕐 {horario}',
                        'callback_data': f'set_envio_{horario.replace(":", "")}'
                    })
                inline_keyboard.append(linha)

            # Adicionar opção personalizada
            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_envio'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao configurar horário de envio: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_verificacao(self, chat_id):
        """Configurar horário de verificação diária"""
        try:
            # Buscar horário atual do usuário
            horario_atual = "09:00"
            try:
                with self.bot.db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute('''
                            SELECT valor FROM configuracoes 
                            WHERE chat_id_usuario = %s AND chave = 'horario_verificacao_diaria'
                        ''', (chat_id,))
                        resultado = cursor.fetchone()
                        if resultado:
                            horario_atual = resultado[0]
            except:
                pass
                
            mensagem = f"""🔔 ALTERAR HORÁRIO DE VERIFICAÇÃO

⏰ Atual: {horario_atual} (Brasília)

Esta verificação acontece uma vez por dia e:
• Verifica todos os clientes vencidos
• Agenda mensagens para envio posterior
• Detecta vencimentos para notificação

💡 CONFIGURAÇÃO SEQUENCIAL RECOMENDADA:
   1. Verificação: 18:00 (detecta vencimentos)
   2. Envio: 18:10 (processa 10 min depois)

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            
            # Horários específicos para verificação incluindo 18:00
            horarios_verificacao = [
                ['06:00', '07:00', '08:00'],
                ['09:00', '12:00', '15:00'],
                ['17:00', '18:00', '19:00'],
                ['20:00', '21:00', '22:00']
            ]
            
            # Adicionar horários de verificação
            for linha_horarios in horarios_verificacao:
                linha = []
                for horario in linha_horarios:
                    linha.append({
                        'text': f'🕐 {horario}',
                        'callback_data': f'set_verificacao_{horario.replace(":", "")}'
                    })
                inline_keyboard.append(linha)

            # Adicionar opção personalizada
            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_verificacao'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao configurar horário de verificação: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_limpeza(self, chat_id):
        """Configurar horário de limpeza da fila"""
        try:
            mensagem = """🧹 ALTERAR HORÁRIO DE LIMPEZA

⏰ Atual: 2:00 AM (Brasília)

Esta limpeza remove mensagens antigas da fila que não foram enviadas.

💡 Recomendação: Madrugada (menos impacto no sistema)

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            horarios = ['01:00', '02:00', '03:00', '04:00', '05:00', '23:00', '00:00']
            
            # Criar botões de horário em linhas de 3
            for i in range(0, len(horarios), 3):
                linha = []
                for j in range(3):
                    if i + j < len(horarios):
                        horario = horarios[i + j]
                        linha.append({'text': horario, 'callback_data': f'set_limpeza_{horario.replace(":", "")}'})
                inline_keyboard.append(linha)

            # Adicionar opção personalizada
            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_limpeza'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao configurar horário de limpeza: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def set_horario_envio(self, chat_id, novo_horario):
        """Define novo horário de envio com isolamento por usuário"""
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            horario_formatado = f"{hora:02d}:{minuto:02d}"
            
            # Salvar configuração com isolamento por usuário
            try:
                with self.bot.db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Deletar configuração existente do usuário
                        cursor.execute('''
                            DELETE FROM configuracoes 
                            WHERE chave = %s AND chat_id_usuario = %s
                        ''', ('horario_envio_diario', chat_id))
                        
                        # Inserir nova configuração
                        cursor.execute('''
                            INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                            VALUES (%s, %s, %s, %s)
                        ''', ('horario_envio_diario', horario_formatado, f'Horário personalizado do usuário', chat_id))
                        
                        conn.commit()
                
                mensagem = f"✅ Horário de envio alterado para {horario_formatado}!\n\n"
                mensagem += "📅 O novo horário foi aplicado ao seu perfil.\n"
                mensagem += "🔄 Configuração ativa imediatamente.\n\n"
                mensagem += f"👤 Usuário: {chat_id} - horário isolado"
                
                self.bot.send_message(chat_id, mensagem)
                # Voltar ao menu de horários
                self.config_horarios_menu(chat_id)
                
            except Exception as db_error:
                logger.error(f"Erro de banco ao salvar horário de envio: {db_error}")
                self.bot.send_message(chat_id, f"❌ Erro no banco: {db_error}")
            
        except Exception as e:
            logger.error(f"Erro ao definir horário de envio: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def set_horario_verificacao(self, chat_id, novo_horario):
        """Define novo horário de verificação com isolamento por usuário"""
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            horario_formatado = f"{hora:02d}:{minuto:02d}"
            
            # Salvar configuração com isolamento por usuário
            try:
                with self.bot.db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Deletar configuração existente do usuário
                        cursor.execute('''
                            DELETE FROM configuracoes 
                            WHERE chave = %s AND chat_id_usuario = %s
                        ''', ('horario_verificacao_diaria', chat_id))
                        
                        # Inserir nova configuração
                        cursor.execute('''
                            INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                            VALUES (%s, %s, %s, %s)
                        ''', ('horario_verificacao_diaria', horario_formatado, f'Horário personalizado do usuário', chat_id))
                        
                        conn.commit()
                
                mensagem = f"✅ Horário de verificação alterado para {horario_formatado}!\n\n"
                mensagem += "📅 O novo horário foi aplicado ao seu perfil.\n"
                mensagem += "🔄 Configuração ativa imediatamente.\n\n"
                mensagem += f"👤 Usuário: {chat_id} - horário isolado"
                
                self.bot.send_message(chat_id, mensagem)
                # Voltar ao menu de horários
                self.config_horarios_menu(chat_id)
                
            except Exception as db_error:
                logger.error(f"Erro de banco ao salvar horário de verificação: {db_error}")
                self.bot.send_message(chat_id, f"❌ Erro no banco: {db_error}")
            
        except Exception as e:
            logger.error(f"Erro ao definir horário de verificação: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def set_horario_limpeza(self, chat_id, novo_horario):
        """Define novo horário de limpeza com isolamento por usuário"""
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            horario_formatado = f"{hora:02d}:{minuto:02d}"
            
            # Salvar configuração com isolamento por usuário
            try:
                with self.bot.db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Deletar configuração existente do usuário
                        cursor.execute('''
                            DELETE FROM configuracoes 
                            WHERE chave = %s AND chat_id_usuario = %s
                        ''', ('horario_limpeza_fila', chat_id))
                        
                        # Inserir nova configuração
                        cursor.execute('''
                            INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                            VALUES (%s, %s, %s, %s)
                        ''', ('horario_limpeza_fila', horario_formatado, f'Horário personalizado do usuário', chat_id))
                        
                        conn.commit()
                
                mensagem = f"✅ Horário de limpeza alterado para {horario_formatado}!\n\n"
                mensagem += "📅 O novo horário foi aplicado ao seu perfil.\n"
                mensagem += "🔄 Configuração ativa imediatamente.\n\n"
                mensagem += f"👤 Usuário: {chat_id} - horário isolado"
                
                self.bot.send_message(chat_id, mensagem)
                # Voltar ao menu de horários
                self.config_horarios_menu(chat_id)
                
            except Exception as db_error:
                logger.error(f"Erro de banco ao salvar horário de limpeza: {db_error}")
                self.bot.send_message(chat_id, f"❌ Erro no banco: {db_error}")
            
        except Exception as e:
            logger.error(f"Erro ao definir horário de limpeza: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def recriar_jobs(self, chat_id):
        """Recria todos os jobs do agendador com limpeza completa"""
        try:
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                # Parar scheduler completamente
                if self.bot.scheduler.running:
                    self.bot.scheduler.scheduler.shutdown(wait=True)
                    self.bot.scheduler.running = False
                
                # Limpar todos os jobs existentes
                jobs = self.bot.scheduler.scheduler.get_jobs()
                for job in jobs:
                    self.bot.scheduler.scheduler.remove_job(job.id)
                
                logger.info(f"Removidos {len(jobs)} jobs existentes")
                
                # Recriar scheduler do zero
                from apscheduler.schedulers.background import BackgroundScheduler
                import pytz
                
                self.bot.scheduler.scheduler = BackgroundScheduler(
                    timezone=pytz.timezone('America/Sao_Paulo'),
                    job_defaults={
                        'coalesce': True,
                        'max_instances': 1,
                        'misfire_grace_time': 300
                    }
                )
                
                # Recriar jobs principais
                self.bot.scheduler._setup_main_jobs()
                
                # Reiniciar scheduler
                self.bot.scheduler.start()
                
                # Verificar jobs criados
                jobs_criados = len(self.bot.scheduler.scheduler.get_jobs())
                
                mensagem = f"✅ Scheduler recriado com sucesso!\n"
                mensagem += f"📊 {jobs_criados} jobs ativos"
                
            else:
                mensagem = "❌ Agendador não disponível."
            
            self.bot.send_message(chat_id, mensagem)
            
        except Exception as e:
            logger.error(f"Erro ao recriar jobs: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao recriar jobs: {str(e)}")
    
    def resetar_horarios_padrao(self, chat_id):
        """Reseta todos os horários para os padrões do sistema"""
        try:
            # Horários padrão do sistema
            horarios_padrao = {
                'horario_envio_diario': '09:00',
                'horario_verificacao_diaria': '09:00', 
                'horario_limpeza_fila': '02:00',
                'timezone_sistema': 'America/Sao_Paulo'
            }
            
            # Salvar configurações padrão ISOLADAS POR USUÁRIO
            for config_key, valor_padrao in horarios_padrao.items():
                if self.bot.db:
                    # CRÍTICO: Isolamento por usuário - cada usuário tem suas próprias configurações
                    self.bot.db.salvar_configuracao(config_key, valor_padrao, chat_id_usuario=chat_id)
            
            # Recriar jobs com os novos horários
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                # Parar scheduler atual
                if self.bot.scheduler.running:
                    self.bot.scheduler.scheduler.shutdown(wait=True)
                    self.bot.scheduler.running = False
                
                # Reiniciar com configurações padrão
                from scheduler_v2_simple import SimpleScheduler
                self.bot.scheduler = SimpleScheduler(self.bot.db, self.bot)
                logger.info(f"Jobs recriados com horários padrão para usuário {chat_id}")
            
            mensagem = f"""✅ SEUS HORÁRIOS FORAM RESETADOS!

🔄 Seus novos horários aplicados:
🕘 Envio Diário: 09:00
   └ Suas mensagens enviadas automaticamente

🕔 Verificação: 09:00  
   └ Verificação dos seus clientes diária

🕚 Limpeza: 02:00
   └ Limpeza da sua fila de mensagens

🌍 Timezone: America/Sao_Paulo

⚡ Status: Jobs recriados automaticamente
📝 Efeito: Imediato - já operacional
🔒 Isolamento: Configurações aplicadas apenas à sua conta

💡 Nota: Estes são os horários padrão otimizados do sistema.
👤 Usuário: {chat_id} - configurações isoladas"""

            inline_keyboard = [
                [
                    {'text': '📊 Verificar Status', 'callback_data': 'status_jobs'},
                    {'text': '⏰ Menu Horários', 'callback_data': 'config_horarios'}
                ],
                [
                    {'text': '🏠 Menu Principal', 'callback_data': 'menu_principal'}
                ]
            ]

            self.bot.send_message(chat_id, mensagem, 
                                reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao resetar horários padrão: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao resetar horários: {str(e)}")

    def limpar_duplicatas(self, chat_id):
        """Remove jobs duplicados deixando apenas os únicos necessários"""
        try:
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                jobs = self.bot.scheduler.scheduler.get_jobs()
                
                # Contar jobs por ID
                job_counts = {}
                jobs_para_remover = []
                
                for job in jobs:
                    if job.id in job_counts:
                        job_counts[job.id] += 1
                        jobs_para_remover.append(job)
                    else:
                        job_counts[job.id] = 1
                
                # Remover duplicatas
                for job in jobs_para_remover:
                    self.bot.scheduler.scheduler.remove_job(job.id)
                
                # Garantir que temos apenas 3 jobs únicos
                jobs_restantes = self.bot.scheduler.scheduler.get_jobs()
                if len(jobs_restantes) != 3:
                    # Recriar jobs do zero se não temos exatamente 3
                    for job in jobs_restantes:
                        self.bot.scheduler.scheduler.remove_job(job.id)
                    
                    self.bot.scheduler._setup_main_jobs()
                
                jobs_final = len(self.bot.scheduler.scheduler.get_jobs())
                mensagem = f"✅ Limpeza concluída!\n📊 Jobs ativos: {jobs_final}"
                
                if len(jobs_para_remover) > 0:
                    mensagem += f"\n🗑️ Removidas {len(jobs_para_remover)} duplicatas"
            
            else:
                mensagem = "❌ Agendador não disponível."
            
            self.bot.send_message(chat_id, mensagem)
            
        except Exception as e:
            logger.error(f"Erro ao limpar duplicatas: {e}")
            self.bot.send_message(chat_id, f"❌ Erro na limpeza: {str(e)}")

    def status_jobs(self, chat_id):
        """Mostra status dos jobs ativos"""
        try:
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                jobs = self.bot.scheduler.scheduler.get_jobs()
                
                mensagem = "📊 STATUS DOS JOBS ATIVOS:\n\n"
                
                for job in jobs:
                    # Corrigir acesso a next_run_time
                    try:
                        # Usar o trigger para calcular próxima execução
                        from datetime import datetime
                        import pytz
                        brasilia = pytz.timezone('America/Sao_Paulo')
                        agora = datetime.now(brasilia)
                        
                        next_run_time = job.trigger.get_next_fire_time(None, agora)
                        if next_run_time:
                            next_run_br = next_run_time.astimezone(brasilia)
                            next_run = next_run_br.strftime('%d/%m %H:%M')
                        else:
                            next_run = 'N/A'
                    except Exception as e:
                        next_run = 'N/A'
                        logger.warning(f"Erro ao calcular próxima execução para {job.id}: {e}")
                    
                    job_name = getattr(job, 'name', job.id)
                    mensagem += f"• {job_name}\n  ID: {job.id}\n  Próxima execução: {next_run}\n\n"
                
                if not jobs:
                    mensagem += "❌ Nenhum job ativo encontrado."
            else:
                mensagem = "❌ Agendador não disponível."
            
            inline_keyboard = [
                [{'text': '🔄 Recriar Jobs', 'callback_data': 'recriar_jobs'}],
                [{'text': '🧹 Limpar Duplicatas', 'callback_data': 'limpar_duplicatas'}],
                [{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}]
            ]
            
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})
            
        except Exception as e:
            logger.error(f"Erro ao mostrar status dos jobs: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar status dos jobs.")

    def horario_personalizado_envio(self, chat_id):
        """Solicita horário personalizado para envio"""
        try:
            mensagem = """⌨️ HORÁRIO PERSONALIZADO - ENVIO

Digite o horário desejado no formato HH:MM

💡 Exemplos:
• 08:30 (8h30 da manhã)
• 14:15 (2h15 da tarde)
• 19:45 (7h45 da noite)

⚠️ Use formato 24 horas (00:00 a 23:59)"""

            # Aguardar resposta do usuário
            self.bot.conversation_states[chat_id] = 'aguardando_horario_envio'
            
            inline_keyboard = [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]
            
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def horario_personalizado_verificacao(self, chat_id):
        """Solicita horário personalizado para verificação"""
        try:
            mensagem = """⌨️ HORÁRIO PERSONALIZADO - VERIFICAÇÃO

Digite o horário desejado no formato HH:MM

💡 Exemplos:
• 05:30 (5h30 da manhã)
• 07:00 (7h da manhã)
• 09:15 (9h15 da manhã)

⚠️ Use formato 24 horas (00:00 a 23:59)"""

            # Aguardar resposta do usuário
            self.bot.conversation_states[chat_id] = 'aguardando_horario_verificacao'
            
            inline_keyboard = [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]
            
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def horario_personalizado_limpeza(self, chat_id):
        """Solicita horário personalizado para limpeza"""
        try:
            mensagem = """⌨️ HORÁRIO PERSONALIZADO - LIMPEZA

Digite o horário desejado no formato HH:MM

💡 Exemplos:
• 01:00 (1h da madrugada)
• 23:30 (11h30 da noite)
• 03:15 (3h15 da madrugada)

⚠️ Use formato 24 horas (00:00 a 23:59)
💡 Recomenda-se madrugada para menos impacto"""

            # Aguardar resposta do usuário
            self.bot.conversation_states[chat_id] = 'aguardando_horario_limpeza'
            
            inline_keyboard = [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]
            
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def processar_horario_personalizado(self, chat_id, texto, estado=None):
        """Processa horário personalizado digitado pelo usuário"""
        try:
            import re
            
            # Validar formato HH:MM
            padrao = r'^([0-1][0-9]|2[0-3]):([0-5][0-9])$'
            if not re.match(padrao, texto):
                self.bot.send_message(chat_id, 
                    "❌ Formato inválido!\n\n"
                    "Use o formato HH:MM (exemplo: 09:30)\n"
                    "Tente novamente:")
                return False
                
            estado = estado or self.bot.conversation_states.get(chat_id)
            
            if estado == 'aguardando_horario_envio':
                horario_sem_dois_pontos = texto.replace(':', '')
                self.set_horario_envio(chat_id, horario_sem_dois_pontos)
                
            elif estado == 'aguardando_horario_verificacao':
                horario_sem_dois_pontos = texto.replace(':', '')
                self.set_horario_verificacao(chat_id, horario_sem_dois_pontos)
                
            elif estado == 'aguardando_horario_limpeza':
                horario_sem_dois_pontos = texto.replace(':', '')
                self.set_horario_limpeza(chat_id, horario_sem_dois_pontos)
                
            else:
                self.bot.send_message(chat_id, "❌ Estado de configuração inválido.")
                return False
            
            # Limpar estado
            if chat_id in self.bot.conversation_states:
                del self.bot.conversation_states[chat_id]
                
            return True
            
        except Exception as e:
            logger.error(f"Erro ao processar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao processar horário.")
            return False
            
    def _get_next_run_time(self, job_id):
        """Obtém próximo horário de execução de um job"""
        try:
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                job = self.bot.scheduler.scheduler.get_job(job_id)
                if job and job.next_run_time:
                    from utils import formatar_datetime_br
                    return formatar_datetime_br(job.next_run_time)
            return "Não agendado"
        except Exception:
            return "Erro ao obter horário"