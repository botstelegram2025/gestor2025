"""
Funções Utilitárias do Sistema
Timezone brasileiro, formatação de dados e funções auxiliares
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
import pytz
import re
from typing import Optional, Union, Dict, Any
# Telegram imports commented out to avoid conflicts
# from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Configurar timezone brasileiro
TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')

logger = logging.getLogger(__name__)

# === FUNÇÕES DE DATA E HORA ===

def agora_br() -> datetime:
    """Retorna datetime atual no fuso horário de Brasília"""
    return datetime.now(TIMEZONE_BR)

def converter_para_br(dt: datetime) -> datetime:
    """Converte datetime para timezone brasileiro"""
    if dt.tzinfo is None:
        # Se não tem timezone, assume UTC
        dt = pytz.utc.localize(dt)
    return dt.astimezone(TIMEZONE_BR)

def formatar_data_br(dt: Union[datetime, date, str]) -> str:
    """Formata data no padrão brasileiro (DD/MM/AAAA)"""
    if isinstance(dt, str):
        try:
            if 'T' in dt:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            else:
                dt = datetime.strptime(dt, '%Y-%m-%d')
        except ValueError:
            return dt
    
    if isinstance(dt, datetime):
        dt = dt.date()
    
    return dt.strftime('%d/%m/%Y')

def formatar_datetime_br(dt: Union[datetime, str]) -> str:
    """Formata data/hora completa no padrão brasileiro"""
    if isinstance(dt, str):
        try:
            if 'T' in dt:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            else:
                dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return dt
    
    if dt.tzinfo is None:
        dt = TIMEZONE_BR.localize(dt)
    else:
        dt = dt.astimezone(TIMEZONE_BR)
    
    return dt.strftime('%d/%m/%Y às %H:%M')

def parsear_data_br(data_str: str) -> Optional[date]:
    """Converte string em formato brasileiro para date"""
    try:
        return datetime.strptime(data_str, '%d/%m/%Y').date()
    except ValueError:
        try:
            return datetime.strptime(data_str, '%d/%m/%y').date()
        except ValueError:
            return None

def calcular_dias_entre(data1: Union[date, str], data2: Union[date, str] = None) -> int:
    """Calcula diferença em dias entre duas datas"""
    if data2 is None:
        data2 = agora_br().date()
    
    if isinstance(data1, str):
        data1 = parsear_data_br(data1) or datetime.strptime(data1, '%Y-%m-%d').date()
    
    if isinstance(data2, str):
        data2 = parsear_data_br(data2) or datetime.strptime(data2, '%Y-%m-%d').date()
    
    return (data1 - data2).days

def adicionar_dias_uteis(data_base: date, dias: int) -> date:
    """Adiciona dias úteis a uma data"""
    data_resultado = data_base
    dias_adicionados = 0
    
    while dias_adicionados < dias:
        data_resultado += timedelta(days=1)
        # 0 = segunda, 6 = domingo
        if data_resultado.weekday() < 5:  # Segunda a sexta
            dias_adicionados += 1
    
    return data_resultado

# === FUNÇÕES DE FORMATAÇÃO ===

def escapar_html(text: Any) -> str:
    """Escapa caracteres especiais para HTML do Telegram"""
    if text is None:
        return ""
    
    text = str(text)
    # Escapar caracteres especiais do HTML
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#x27;')
    return text

def escapar_markdown(text: Any) -> str:
    """Escapa caracteres especiais para Markdown do Telegram"""
    if text is None:
        return ""
    
    text = str(text)
    # Caracteres que precisam ser escapados no Markdown
    chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in chars_to_escape:
        text = text.replace(char, f'\\{char}')
    
    return text

def formatar_moeda(valor: Union[float, int, str]) -> str:
    """Formata valor monetário no padrão brasileiro"""
    try:
        if isinstance(valor, str):
            valor = float(valor.replace(',', '.'))
        
        return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return "R$ 0,00"

def houve_conversao_telefone(telefone_original: str, telefone_padronizado: str) -> bool:
    """
    Verifica se houve conversão no telefone (formato original diferente do padronizado)
    """
    if not telefone_original or not telefone_padronizado:
        return False
    
    # Limpar formato original para comparação
    original_limpo = re.sub(r'\D', '', str(telefone_original))
    
    # Remover código do país se presente no original
    if original_limpo.startswith('55') and len(original_limpo) >= 12:
        original_limpo = original_limpo[2:]
    
    # Remover 0 à esquerda do DDD se presente
    if original_limpo.startswith('0') and len(original_limpo) == 11:
        original_limpo = original_limpo[1:]
    
    return original_limpo != telefone_padronizado

def padronizar_telefone(telefone: str) -> str:
    """
    Padroniza número de telefone para o formato Baileys WhatsApp: DDD12345678 (DDD + 8 dígitos)
    
    Aceita qualquer formato de entrada:
    - (11) 99999-9999 → 1199999999
    - 11 99999-9999 → 1199999999  
    - 11999999999 → 1199999999
    - +55 11 99999-9999 → 1199999999
    - +5511999999999 → 1199999999
    - 5511999999999 → 1199999999
    - 011999999999 → 1199999999
    
    IMPORTANTE: Baileys aceita apenas DDD + 8 dígitos (formato antigo)
    Se número moderno (9 dígitos) é informado, remove o primeiro 9
    
    Retorna sempre no formato: DDD12345678 (10 dígitos totais)
    """
    if not telefone:
        return ""
    
    # Remover todos os caracteres não numéricos
    apenas_numeros = re.sub(r'\D', '', str(telefone))
    
    # Se não tem números suficientes, retornar original
    if len(apenas_numeros) < 10:
        return telefone
    
    # Remover código do país (+55) se presente
    if apenas_numeros.startswith('55') and len(apenas_numeros) >= 12:
        apenas_numeros = apenas_numeros[2:]
    
    # Remover 0 à esquerda do DDD se presente (0XX para XX)
    if apenas_numeros.startswith('0') and len(apenas_numeros) == 11:
        apenas_numeros = apenas_numeros[1:]
    
    # Validar se tem pelo menos 10 dígitos
    if len(apenas_numeros) < 10:
        return telefone
    
    # CONVERSÃO PARA FORMATO BAILEYS (DDD + 8 DÍGITOS)
    if len(apenas_numeros) == 10:
        # Já está no formato correto: DDD + 8 dígitos
        return apenas_numeros
    elif len(apenas_numeros) == 11:
        # Formato moderno (DDD + 9 dígitos) → remover primeiro 9
        ddd = apenas_numeros[:2]
        numero = apenas_numeros[2:]
        
        # Se começa com 9, remover para ficar com 8 dígitos
        if numero.startswith('9'):
            numero = numero[1:]  # Remove o primeiro 9
        
        return ddd + numero
    else:
        # Se tem mais dígitos, pegar DDD + últimos 8 dígitos
        if len(apenas_numeros) > 11:
            # Pegar últimos 10 dígitos (DDD + 8)
            apenas_numeros = apenas_numeros[-10:]
        
        return apenas_numeros

def validar_telefone_whatsapp(telefone: str) -> bool:
    """
    Valida se o telefone está no formato correto do Baileys WhatsApp (DDD12345678 - 10 dígitos)
    """
    telefone_padronizado = padronizar_telefone(telefone)
    
    # Verificar se tem exatamente 10 dígitos (DDD + 8 dígitos)
    if len(telefone_padronizado) != 10:
        return False
    
    # Verificar se é só números
    if not telefone_padronizado.isdigit():
        return False
    
    # Verificar se o DDD é válido (11 a 99)
    ddd = telefone_padronizado[:2]
    try:
        ddd_num = int(ddd)
        if not (11 <= ddd_num <= 99):
            return False
    except:
        return False
    
    # Verificar se tem 8 dígitos após o DDD
    numero = telefone_padronizado[2:]
    if len(numero) != 8:
        return False
    
    return True

def formatar_telefone_exibicao(telefone: str) -> str:
    """
    Formata telefone para exibição amigável: (11) 9999-9999 (formato Baileys)
    """
    telefone_padrao = padronizar_telefone(telefone)
    
    if len(telefone_padrao) == 10:
        ddd = telefone_padrao[:2]
        parte1 = telefone_padrao[2:6]  # 4 dígitos
        parte2 = telefone_padrao[6:]   # 4 dígitos
        return f"({ddd}) {parte1}-{parte2}"
    
    return telefone

def formatar_telefone(telefone: str) -> str:
    """Formata telefone no padrão brasileiro (função legada)"""
    if not telefone:
        return ""
    
    # Remover caracteres não numéricos
    numeros = re.sub(r'\D', '', telefone)
    
    # Formatação baseada no tamanho
    if len(numeros) == 11:  # Celular com 9
        return f"({numeros[:2]}) {numeros[2:7]}-{numeros[7:]}"
    elif len(numeros) == 10:  # Fixo ou celular sem 9
        return f"({numeros[:2]}) {numeros[2:6]}-{numeros[6:]}"
    elif len(numeros) == 13 and numeros.startswith('55'):  # Com código do país
        numeros = numeros[2:]  # Remove código do país
        if len(numeros) == 11:
            return f"+55 ({numeros[:2]}) {numeros[2:7]}-{numeros[7:]}"
        elif len(numeros) == 10:
            return f"+55 ({numeros[:2]}) {numeros[2:6]}-{numeros[6:]}"
    
    return telefone

def limpar_telefone(telefone: str) -> str:
    """Remove formatação do telefone mantendo apenas números"""
    if not telefone:
        return ""
    
    return re.sub(r'\D', '', telefone)

def validar_telefone(telefone: str) -> bool:
    """Valida se telefone está em formato válido"""
    numeros = limpar_telefone(telefone)
    
    # Verificar tamanhos válidos
    if len(numeros) in [10, 11]:  # Sem código do país
        return True
    elif len(numeros) in [12, 13] and numeros.startswith('55'):  # Com código do país
        return True
    
    return False

def validar_email(email: str) -> bool:
    """Valida formato de email"""
    if not email:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def formatar_cpf(cpf: str) -> str:
    """Formata CPF"""
    if not cpf:
        return ""
    
    numeros = re.sub(r'\D', '', cpf)
    
    if len(numeros) == 11:
        return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
    
    return cpf

def validar_cpf(cpf: str) -> bool:
    """Valida CPF"""
    cpf = re.sub(r'\D', '', cpf)
    
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    
    # Validar dígitos verificadores
    for i in range(9, 11):
        soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if int(cpf[i]) != digito:
            return False
    
    return True

# === FUNÇÕES DE TECLADOS (COMENTADAS - DEPENDEM DO TELEGRAM) ===

def criar_teclado_principal():  # -> ReplyKeyboardMarkup:
    """Cria o teclado persistente com os botões principais organizados"""
    # Função comentada até resolver problema de imports telegram
    return None
    # keyboard = [
    #     # Gestão de Clientes
    #     [
    #         KeyboardButton("👥 Listar Clientes"),
    #         KeyboardButton("➕ Adicionar Cliente")
    #     ],
    #     [KeyboardButton("🔍 Buscar Cliente"),
    #      KeyboardButton("📊 Relatórios")],
    # 
    #     # Sistema de Mensagens
    #     [KeyboardButton("📄 Templates"),
    #      KeyboardButton("⏰ Agendador")],
    #     [
    #         KeyboardButton("📋 Fila de Mensagens"),
    #         KeyboardButton("📜 Logs de Envios")
    #     ],
    # 
    #     # WhatsApp
    #     [
    #         KeyboardButton("📱 WhatsApp Status"),
    #         KeyboardButton("🧪 Testar WhatsApp")
    #     ],
    #     [KeyboardButton("📱 QR Code"),
    #      KeyboardButton("⚙️ Gerenciar WhatsApp")],
    # 
    #     # Configurações
    #     [
    #         KeyboardButton("🏢 Empresa"),
    #         KeyboardButton("💳 PIX"),
    #         KeyboardButton("📞 Suporte")
    #     ],
    #     [KeyboardButton("❓ Ajuda")]
    # ]
    # return ReplyKeyboardMarkup(keyboard,
    #                            resize_keyboard=True,
    #                            one_time_keyboard=False)

def criar_teclado_cancelar():  # -> ReplyKeyboardMarkup:
    """Cria teclado com opção de cancelar"""
    return None  # Função comentada até resolver problema de imports telegram

def criar_teclado_confirmar():  # -> ReplyKeyboardMarkup:
    """Cria teclado para confirmação"""
    return None  # Função comentada até resolver problema de imports telegram

def criar_teclado_planos():  # -> ReplyKeyboardMarkup:
    """Cria teclado com planos predefinidos"""
    return None  # Função comentada até resolver problema de imports telegram

def criar_teclado_vencimento():  # -> ReplyKeyboardMarkup:
    """Cria teclado para vencimento automático ou personalizado"""
    return None  # Função comentada até resolver problema de imports telegram

def criar_teclado_valores():  # -> ReplyKeyboardMarkup:
    """Cria teclado com valores predefinidos"""
    return None  # Função comentada até resolver problema de imports telegram

def criar_teclado_edicao():  # -> ReplyKeyboardMarkup:
    """Cria teclado para edição de campos"""
    return None  # Função comentada até resolver problema de imports telegram

def criar_teclado_inline_paginacao(pagina_atual: int, total_paginas: int, prefix: str = "page"):  # -> InlineKeyboardMarkup:
    """Cria teclado inline para paginação"""
    return None  # Função comentada até resolver problema de imports telegram

# === FUNÇÕES DE VALIDAÇÃO ===

def validar_valor_monetario(valor_str: str) -> Optional[float]:
    """Valida e converte string para valor monetário"""
    try:
        # Remover símbolos monetários e espaços
        valor_limpo = valor_str.replace('R$', '').replace(' ', '').strip()
        
        # Trocar vírgula por ponto se necessário
        if ',' in valor_limpo and '.' not in valor_limpo:
            valor_limpo = valor_limpo.replace(',', '.')
        elif ',' in valor_limpo and '.' in valor_limpo:
            # Formato brasileiro: 1.000,50
            valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
        
        valor = float(valor_limpo)
        
        if valor <= 0:
            return None
        
        return round(valor, 2)
        
    except (ValueError, TypeError):
        return None

def validar_data_brasileira(data_str: str) -> Optional[date]:
    """Valida data em formato brasileiro"""
    try:
        return datetime.strptime(data_str, '%d/%m/%Y').date()
    except ValueError:
        try:
            return datetime.strptime(data_str, '%d/%m/%y').date()
        except ValueError:
            return None

def validar_nome(nome: str) -> bool:
    """Valida nome (mínimo 2 caracteres, apenas letras e espaços)"""
    if not nome or len(nome.strip()) < 2:
        return False
    
    # Permite apenas letras, espaços, acentos e hífens
    pattern = r'^[a-zA-ZÀ-ÿ\s\-]+$'
    return re.match(pattern, nome.strip()) is not None

# === FUNÇÕES DE TEXTO ===

def truncar_texto(texto: str, limite: int = 100, sufixo: str = "...") -> str:
    """Trunca texto mantendo palavras completas"""
    if len(texto) <= limite:
        return texto
    
    texto_truncado = texto[:limite - len(sufixo)]
    
    # Encontrar o último espaço para não cortar palavras
    ultimo_espaco = texto_truncado.rfind(' ')
    if ultimo_espaco > 0:
        texto_truncado = texto_truncado[:ultimo_espaco]
    
    return texto_truncado + sufixo

def capitalizar_nome(nome: str) -> str:
    """Capitaliza nome próprio corretamente"""
    if not nome:
        return ""
    
    # Palavras que devem ficar em minúsculo
    minusculas = ['da', 'de', 'do', 'dos', 'das', 'e', 'em', 'na', 'no', 'pela', 'pelo']
    
    palavras = nome.lower().split()
    resultado = []
    
    for i, palavra in enumerate(palavras):
        if i == 0 or palavra not in minusculas:
            resultado.append(palavra.capitalize())
        else:
            resultado.append(palavra)
    
    return ' '.join(resultado)

def extrair_numeros(texto: str) -> str:
    """Extrai apenas números de um texto"""
    return re.sub(r'\D', '', texto)

def gerar_slug(texto: str) -> str:
    """Gera slug a partir de texto"""
    import unicodedata
    
    # Remover acentos
    texto_sem_acento = unicodedata.normalize('NFKD', texto)
    texto_sem_acento = ''.join([c for c in texto_sem_acento if not unicodedata.combining(c)])
    
    # Converter para minúsculo e substituir espaços e caracteres especiais
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', texto_sem_acento.lower())
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = slug.strip('-')
    
    return slug

# === FUNÇÕES DE SISTEMA ===

def verificar_ambiente() -> Dict[str, Any]:
    """Verifica configurações do ambiente"""
    info = {
        'python_version': sys.version,
        'timezone': str(TIMEZONE_BR),
        'data_atual': formatar_datetime_br(agora_br()),
        'variaveis_ambiente': {}
    }
    
    # Verificar variáveis importantes
    vars_importantes = [
        'BOT_TOKEN', 'ADMIN_CHAT_ID', 'ADMIN_PHONE',
        'PGHOST', 'PGDATABASE', 'PGUSER', 'PGPASSWORD', 'PGPORT',
        'BAILEYS_API_URL', 'BAILEYS_API_KEY', 'BAILEYS_SESSION'
    ]
    
    for var in vars_importantes:
        valor = os.getenv(var)
        if valor:
            # Mascarar valores sensíveis
            if 'TOKEN' in var or 'PASSWORD' in var or 'KEY' in var:
                info['variaveis_ambiente'][var] = f"{valor[:5]}..." if len(valor) > 5 else "***"
            else:
                info['variaveis_ambiente'][var] = valor
        else:
            info['variaveis_ambiente'][var] = None
    
    return info

def log_performance(func_name: str, start_time: datetime, end_time: datetime = None):
    """Log de performance de funções"""
    if end_time is None:
        end_time = agora_br()
    
    duracao = (end_time - start_time).total_seconds()
    
    if duracao > 5.0:  # Log apenas se demorou mais de 5 segundos
        logger.warning(f"Performance: {func_name} demorou {duracao:.2f}s")
    elif duracao > 1.0:  # Log info se demorou mais de 1 segundo
        logger.info(f"Performance: {func_name} demorou {duracao:.2f}s")

# === CLASSES AUXILIARES ===

class Timer:
    """Classe para medir tempo de execução"""
    
    def __init__(self, nome: str = "Timer"):
        self.nome = nome
        self.inicio = None
    
    def __enter__(self):
        self.inicio = agora_br()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.inicio:
            fim = agora_br()
            duracao = (fim - self.inicio).total_seconds()
            logger.debug(f"{self.nome}: {duracao:.3f}s")

class Paginacao:
    """Classe para controle de paginação"""
    
    def __init__(self, total_itens: int, itens_por_pagina: int = 10):
        self.total_itens = total_itens
        self.itens_por_pagina = itens_por_pagina
        self.total_paginas = max(1, (total_itens + itens_por_pagina - 1) // itens_por_pagina)
    
    def obter_itens_pagina(self, lista_itens: list, pagina: int):
        """Obtém itens de uma página específica"""
        pagina = max(1, min(pagina, self.total_paginas))
        inicio = (pagina - 1) * self.itens_por_pagina
        fim = inicio + self.itens_por_pagina
        
        return {
            'itens': lista_itens[inicio:fim],
            'pagina_atual': pagina,
            'total_paginas': self.total_paginas,
            'total_itens': self.total_itens,
            'tem_anterior': pagina > 1,
            'tem_proximo': pagina < self.total_paginas
        }

# === DECORATORS ===

def retry(max_tentativas: int = 3, delay: float = 1.0):
    """Decorator para retry automático de funções"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for tentativa in range(max_tentativas):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if tentativa == max_tentativas - 1:
                        raise e
                    logger.warning(f"Tentativa {tentativa + 1} falhou para {func.__name__}: {e}")
                    if delay > 0:
                        import time
                        time.sleep(delay)
            return None
        return wrapper
    return decorator

def medir_tempo(func):
    """Decorator para medir tempo de execução"""
    def wrapper(*args, **kwargs):
        inicio = agora_br()
        try:
            resultado = func(*args, **kwargs)
            return resultado
        finally:
            fim = agora_br()
            log_performance(func.__name__, inicio, fim)
    return wrapper

# === CONSTANTES ===

STATUS_VENCIMENTO_ICONS = {
    'em_dia': '🟢',
    'vence_em_breve': '🟡',
    'vence_hoje': '🟠',
    'vencido': '🔴'
}

MESES_ABREV = {
    1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
    7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
}

DIAS_SEMANA = {
    0: 'Segunda', 1: 'Terça', 2: 'Quarta', 3: 'Quinta',
    4: 'Sexta', 5: 'Sábado', 6: 'Domingo'
}

# Exportar funções principais
__all__ = [
    'agora_br', 'converter_para_br', 'formatar_data_br', 'formatar_datetime_br',
    'escapar_html', 'escapar_markdown', 'formatar_moeda', 'formatar_telefone',
    'criar_teclado_principal', 'criar_teclado_cancelar', 'criar_teclado_confirmar',
    'validar_telefone', 'validar_email', 'validar_cpf', 'Timer', 'Paginacao'
]
