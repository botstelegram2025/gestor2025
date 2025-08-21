"""
Sistema de Gerenciamento de Templates
Gerencia templates de mensagens com suporte a variáveis dinâmicas e processamento
"""

import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from utils import formatar_data_br, formatar_datetime_br, agora_br

logger = logging.getLogger(__name__)

class TemplateManager:
    def __init__(self, database_manager):
        """Inicializa o gerenciador de templates"""
        self.db = database_manager
        
        # Variáveis disponíveis para templates
        self.variaveis_disponíveis = {
            'nome': 'Nome do cliente',
            'telefone': 'Telefone do cliente',
            'pacote': 'Pacote/plano do cliente',
            'valor': 'Valor mensal do plano',
            'servidor': 'Servidor/login do cliente',
            'vencimento': 'Data de vencimento formatada (DD/MM/AAAA)',
            'vencimento_extenso': 'Data de vencimento por extenso',
            'dias_para_vencer': 'Dias restantes para vencer',
            'status_vencimento': 'Status do vencimento',
            'data_atual': 'Data atual formatada',
            'hora_atual': 'Data e hora atual formatada',
            'empresa_nome': 'Nome da empresa',
            'empresa_telefone': 'Telefone da empresa',
            'empresa_email': 'Email da empresa',
            'suporte_telefone': 'Telefone de suporte',
            'suporte_email': 'Email de suporte',
            'pix_chave': 'Chave PIX para pagamento',
            'pix_beneficiario': 'Nome do beneficiário PIX'
        }
    
    def listar_templates(self, apenas_ativos=True, chat_id_usuario=None):
        """Lista templates com isolamento por usuário"""
        try:
            return self.db.listar_templates(apenas_ativos, chat_id_usuario)
        except Exception as e:
            logger.error(f"Erro ao listar templates: {e}")
            return []
    
    def obter_template(self, template_id, chat_id_usuario=None):
        """Obtém template por ID com isolamento por usuário"""
        try:
            return self.db.obter_template(template_id, chat_id_usuario)
        except Exception as e:
            logger.error(f"Erro ao obter template {template_id}: {e}")
            return None
    
    def buscar_template_por_id(self, template_id, chat_id_usuario=None):
        """Busca template por ID com isolamento por usuário"""
        try:
            return self.db.obter_template(template_id, chat_id_usuario)
        except Exception as e:
            logger.error(f"Erro ao buscar template {template_id}: {e}")
            return None
    
    def buscar_template(self, template_id, chat_id_usuario=None):
        """Busca template por ID com isolamento por usuário"""
        try:
            return self.db.obter_template(template_id, chat_id_usuario)
        except Exception as e:
            logger.error(f"Erro ao buscar template {template_id}: {e}")
            return None
    
    def excluir_template(self, template_id, chat_id_usuario=None):
        """Exclui template definitivamente com isolamento por usuário"""
        try:
            self.db.excluir_template(template_id, chat_id_usuario)
            return True
        except Exception as e:
            logger.error(f"Erro ao excluir template {template_id}: {e}")
            return False
    
    def atualizar_campo(self, template_id, campo, valor, chat_id_usuario=None):
        """Atualiza campo específico do template com isolamento por usuário"""
        try:
            return self.db.atualizar_template_campo(template_id, campo, valor, chat_id_usuario)
        except Exception as e:
            logger.error(f"Erro ao atualizar campo {campo} do template {template_id}: {e}")
            return False
    
    def obter_template_por_tipo(self, tipo, chat_id_usuario=None):
        """Obtém template por tipo com isolamento por usuário"""
        try:
            return self.db.obter_template_por_tipo(tipo, chat_id_usuario)
        except Exception as e:
            logger.error(f"Erro ao obter template por tipo {tipo}: {e}")
            return None
    
    def criar_template(self, nome, conteudo, tipo='geral', descricao=None, chat_id_usuario=None):
        """Cria novo template com isolamento por usuário"""
        try:
            # Validar conteúdo do template
            erros_validacao = self.validar_template(conteudo)
            if erros_validacao:
                raise ValueError(f"Erros no template: {', '.join(erros_validacao)}")
            
            template_id = self.db.criar_template(nome, descricao, conteudo, tipo, chat_id_usuario)
            logger.info(f"Template criado: {nome} (ID: {template_id}), Usuário: {chat_id_usuario}")
            return template_id
            
        except Exception as e:
            logger.error(f"Erro ao criar template: {e}")
            raise
    
    def atualizar_template(self, template_id, nome=None, descricao=None, conteudo=None, chat_id_usuario=None):
        """Atualiza template existente com isolamento por usuário"""
        try:
            # Validar conteúdo se fornecido
            if conteudo:
                erros_validacao = self.validar_template(conteudo)
                if erros_validacao:
                    raise ValueError(f"Erros no template: {', '.join(erros_validacao)}")
            
            sucesso = self.db.atualizar_template(template_id, nome, descricao, conteudo, chat_id_usuario)
            if sucesso:
                logger.info(f"Template {template_id} atualizado com sucesso para usuário {chat_id_usuario}")
            return sucesso
            
        except Exception as e:
            logger.error(f"Erro ao atualizar template: {e}")
            raise
    
    def validar_template(self, conteudo):
        """Valida conteúdo do template verificando variáveis"""
        erros = []
        
        # Encontrar todas as variáveis no template
        variaveis_encontradas = re.findall(r'\{(\w+)\}', conteudo)
        
        # Verificar se todas as variáveis são válidas
        for variavel in variaveis_encontradas:
            if variavel not in self.variaveis_disponíveis:
                erros.append(f"Variável desconhecida: {{{variavel}}}")
        
        # Verificar balanceamento de chaves
        abertas = conteudo.count('{')
        fechadas = conteudo.count('}')
        if abertas != fechadas:
            erros.append("Chaves desbalanceadas no template")
        
        return erros
    
    def processar_template(self, conteudo, cliente_data, configuracoes=None):
        """Processa template substituindo variáveis pelos dados reais"""
        try:
            # Preparar dados para substituição
            dados = self._preparar_dados_cliente(cliente_data, configuracoes)
            
            # Substituir variáveis
            texto_processado = conteudo
            
            for variavel, valor in dados.items():
                placeholder = f"{{{variavel}}}"
                if placeholder in texto_processado:
                    texto_processado = texto_processado.replace(placeholder, str(valor))
            
            return texto_processado
            
        except Exception as e:
            logger.error(f"Erro ao processar template: {e}")
            return conteudo  # Retorna o template original em caso de erro
    
    def _preparar_dados_cliente(self, cliente_data, configuracoes=None):
        """Prepara dados do cliente para substituição no template"""
        dados = {}
        
        # Dados básicos do cliente
        dados['nome'] = cliente_data.get('nome', '')
        dados['telefone'] = cliente_data.get('telefone', '')
        dados['pacote'] = cliente_data.get('pacote', '')
        dados['valor'] = f"{cliente_data.get('valor', 0):.2f}".replace('.', ',')
        dados['servidor'] = cliente_data.get('servidor', '')
        
        # Formatação de datas
        vencimento = cliente_data.get('vencimento')
        if vencimento:
            if isinstance(vencimento, str):
                try:
                    vencimento = datetime.strptime(vencimento, '%Y-%m-%d').date()
                except:
                    pass
            
            dados['vencimento'] = formatar_data_br(vencimento)
            dados['vencimento_extenso'] = self._data_por_extenso(vencimento)
        else:
            dados['vencimento'] = 'Não definido'
            dados['vencimento_extenso'] = 'Não definido'
        
        # Cálculos de vencimento
        dias_vencimento = cliente_data.get('dias_vencimento')
        if dias_vencimento is not None:
            if dias_vencimento < 0:
                dados['dias_para_vencer'] = f"Vencido há {abs(dias_vencimento)} dias"
                dados['status_vencimento'] = "VENCIDO"
            elif dias_vencimento == 0:
                dados['dias_para_vencer'] = "Vence hoje"
                dados['status_vencimento'] = "VENCE HOJE"
            else:
                dados['dias_para_vencer'] = f"{dias_vencimento} dias"
                dados['status_vencimento'] = "EM DIA"
        else:
            dados['dias_para_vencer'] = "Não calculado"
            dados['status_vencimento'] = "INDEFINIDO"
        
        # Data e hora atual
        agora = agora_br()
        dados['data_atual'] = formatar_data_br(agora.date())
        dados['hora_atual'] = formatar_datetime_br(agora)
        
        # Configurações da empresa (com fallbacks)
        if configuracoes is None:
            configuracoes = self._obter_configuracoes_empresa()
        
        dados['empresa_nome'] = configuracoes.get('empresa_nome', '[CONFIGURAR NOME DA EMPRESA]')
        dados['empresa_telefone'] = configuracoes.get('empresa_telefone', '[CONFIGURAR TELEFONE]')
        dados['empresa_email'] = configuracoes.get('empresa_email', '[CONFIGURAR EMAIL]')
        dados['suporte_telefone'] = configuracoes.get('suporte_telefone', '[CONFIGURAR SUPORTE]')
        dados['suporte_email'] = configuracoes.get('suporte_email', '[CONFIGURAR EMAIL SUPORTE]')
        dados['pix_chave'] = configuracoes.get('pix_chave', '[CONFIGURAR CHAVE PIX]')
        dados['pix_beneficiario'] = configuracoes.get('pix_beneficiario', '[CONFIGURAR BENEFICIÁRIO]')
        
        return dados
    
    def _obter_configuracoes_empresa(self):
        """Obtém configurações da empresa do banco de dados"""
        try:
            config = {}
            
            # Buscar configurações principais
            config['empresa_nome'] = self.db.obter_configuracao('empresa_nome', '[CONFIGURAR EMPRESA]')
            config['empresa_telefone'] = self.db.obter_configuracao('empresa_telefone', '[CONFIGURAR TELEFONE]')
            config['empresa_email'] = self.db.obter_configuracao('empresa_email', '[CONFIGURAR EMAIL]')
            config['suporte_telefone'] = self.db.obter_configuracao('suporte_telefone', '[CONFIGURAR SUPORTE]')
            config['suporte_email'] = self.db.obter_configuracao('suporte_email', '[CONFIGURAR EMAIL SUPORTE]')
            config['pix_chave'] = self.db.obter_configuracao('pix_chave', '[CONFIGURAR PIX]')
            config['pix_beneficiario'] = self.db.obter_configuracao('pix_beneficiario', '[CONFIGURAR BENEFICIÁRIO]')
            
            return config
            
        except Exception as e:
            logger.error(f"Erro ao obter configurações da empresa: {e}")
            return {}
    
    def _data_por_extenso(self, data):
        """Converte data para formato por extenso"""
        try:
            meses = [
                '', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
                'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'
            ]
            
            if isinstance(data, str):
                data = datetime.strptime(data, '%Y-%m-%d').date()
            
            return f"{data.day} de {meses[data.month]} de {data.year}"
            
        except Exception as e:
            logger.error(f"Erro ao converter data por extenso: {e}")
            return str(data)
    
    def obter_variaveis_disponíveis(self):
        """Retorna lista de variáveis disponíveis para templates"""
        return self.variaveis_disponíveis
    
    def gerar_preview_template(self, conteudo, usar_dados_exemplo=True):
        """Gera preview do template com dados de exemplo"""
        try:
            if usar_dados_exemplo:
                # Dados de exemplo para preview
                exemplo_cliente = {
                    'nome': 'João Silva',
                    'telefone': '11999999999',
                    'pacote': 'Netflix Premium',
                    'valor': 45.90,
                    'servidor': 'joao.silva@email.com',
                    'vencimento': '2024-02-15',
                    'dias_vencimento': 3
                }
                
                exemplo_config = {
                    'empresa_nome': 'Streaming Premium',
                    'empresa_telefone': '11888888888',
                    'empresa_email': 'contato@streaming.com',
                    'suporte_telefone': '11777777777',
                    'pix_chave': '11999999999',
                    'pix_beneficiario': 'Streaming Premium LTDA'
                }
                
                return self.processar_template(conteudo, exemplo_cliente, exemplo_config)
            else:
                return conteudo
                
        except Exception as e:
            logger.error(f"Erro ao gerar preview: {e}")
            return conteudo
    
    def duplicar_template(self, template_id, novo_nome):
        """Duplica um template existente"""
        try:
            template_original = self.obter_template(template_id)
            if not template_original:
                raise ValueError("Template original não encontrado")
            
            novo_template_id = self.criar_template(
                nome=novo_nome,
                descricao=f"Cópia de: {template_original['descricao']}",
                conteudo=template_original['conteudo'],
                tipo=template_original['tipo']
            )
            
            logger.info(f"Template duplicado: {template_original['nome']} -> {novo_nome}")
            return novo_template_id
            
        except Exception as e:
            logger.error(f"Erro ao duplicar template: {e}")
            raise
    
    def exportar_templates(self, formato='json'):
        """Exporta todos os templates para backup"""
        try:
            templates = self.listar_templates(apenas_ativos=False)
            
            if formato.lower() == 'json':
                import json
                return json.dumps(templates, indent=2, default=str, ensure_ascii=False)
            else:
                raise ValueError("Formato não suportado. Use 'json'")
                
        except Exception as e:
            logger.error(f"Erro ao exportar templates: {e}")
            raise
    
    def importar_templates(self, dados_json):
        """Importa templates de backup"""
        try:
            import json
            templates = json.loads(dados_json)
            
            importados = 0
            erros = []
            
            for template in templates:
                try:
                    # Verificar se já existe
                    nome_original = template['nome']
                    contador = 1
                    nome_final = nome_original
                    
                    while any(t['nome'] == nome_final for t in self.listar_templates(apenas_ativos=False)):
                        nome_final = f"{nome_original} ({contador})"
                        contador += 1
                    
                    self.criar_template(
                        nome=nome_final,
                        descricao=template.get('descricao', ''),
                        conteudo=template['conteudo'],
                        tipo=template.get('tipo', 'geral')
                    )
                    importados += 1
                    
                except Exception as e:
                    erros.append(f"Template '{template.get('nome', 'Unknown')}': {str(e)}")
            
            logger.info(f"Templates importados: {importados}, Erros: {len(erros)}")
            return {'importados': importados, 'erros': erros}
            
        except Exception as e:
            logger.error(f"Erro ao importar templates: {e}")
            raise
    
    def obter_estatisticas_templates(self):
        """Obtém estatísticas de uso dos templates"""
        try:
            templates = self.listar_templates(apenas_ativos=False)
            
            stats = {
                'total': len(templates),
                'ativos': len([t for t in templates if t['ativo']]),
                'inativos': len([t for t in templates if not t['ativo']]),
                'mais_usado': None,
                'menos_usado': None,
                'uso_total': sum(t['uso_count'] for t in templates),
                'tipos': {}
            }
            
            # Mais e menos usado
            if templates:
                templates_ordenados = sorted(templates, key=lambda x: x['uso_count'], reverse=True)
                stats['mais_usado'] = templates_ordenados[0]['nome'] if templates_ordenados else None
                stats['menos_usado'] = templates_ordenados[-1]['nome'] if templates_ordenados else None
            
            # Estatísticas por tipo
            for template in templates:
                tipo = template['tipo']
                if tipo not in stats['tipos']:
                    stats['tipos'][tipo] = {'count': 0, 'uso_total': 0}
                stats['tipos'][tipo]['count'] += 1
                stats['tipos'][tipo]['uso_total'] += template['uso_count']
            
            return stats
            
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {}
    
    def buscar_templates(self, termo):
        """Busca templates por nome ou conteúdo"""
        try:
            templates = self.listar_templates(apenas_ativos=False)
            termo_lower = termo.lower()
            
            resultados = []
            for template in templates:
                if (termo_lower in template['nome'].lower() or 
                    termo_lower in template['descricao'].lower() or 
                    termo_lower in template['conteudo'].lower()):
                    resultados.append(template)
            
            return resultados
            
        except Exception as e:
            logger.error(f"Erro ao buscar templates: {e}")
            return []
    
    def incrementar_uso_template(self, template_id):
        """Incrementa contador de uso do template"""
        try:
            return self.db.incrementar_uso_template(template_id)
        except Exception as e:
            logger.error(f"Erro ao incrementar uso do template {template_id}: {e}")
            return False
