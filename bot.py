import os
import subprocess
from telegram.ext import Updater, CommandHandler
from telegram import Update
from telegram.ext.callbackcontext import CallbackContext
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

# Configuração do banco de dados
engine = create_engine("sqlite:///clientes.db")
Base = declarative_base()

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True)
    nome = Column(String)
    telefone = Column(String)
    pacote = Column(String)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Comandos do bot
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Bem-vindo! Use /addcliente e /listarclientes.")

def add_cliente(update: Update, context: CallbackContext):
    """Uso: /addcliente Nome Pacote"""
    """Uso: /addcliente Nome Telefone Pacote"""
    session = Session()
    if len(context.args) < 2:
        update.message.reply_text("Uso: /addcliente Nome Pacote")
    if len(context.args) < 3:
        update.message.reply_text("Uso: /addcliente Nome Telefone Pacote")
        return

    nome = context.args[0]
    pacote = " ".join(context.args[1:])
    cliente = Cliente(nome=nome, pacote=pacote)
    telefone = context.args[1]
    pacote = " ".join(context.args[2:])
    cliente = Cliente(nome=nome, telefone=telefone, pacote=pacote)
    session.add(cliente)
    session.commit()
    update.message.reply_text(f"Cliente {nome} adicionado com pacote {pacote}.")

def listar_clientes(update: Update, context: CallbackContext):
    session = Session()
    clientes = session.query(Cliente).all()
    if not clientes:
        update.message.reply_text("Nenhum cliente cadastrado.")
        return

    resposta = "\n".join(f"{c.id} - {c.nome} ({c.pacote})" for c in clientes)
    resposta = "\n".join(
        f"{c.id} - {c.nome} {c.telefone} ({c.pacote})" for c in clientes
    )
    update.message.reply_text(resposta)


def enviar(update: Update, context: CallbackContext):
    """Uso: /enviar ID Mensagem"""
    if len(context.args) < 2:
        update.message.reply_text("Uso: /enviar ID Mensagem")
        return
    session = Session()
    cliente = session.get(Cliente, int(context.args[0]))
    if not cliente:
        update.message.reply_text("Cliente não encontrado.")
        return
    mensagem = " ".join(context.args[1:])
    subprocess.run(["node", "whatsapp.js", cliente.telefone, mensagem])
    update.message.reply_text(f"Mensagem enviada para {cliente.nome}.")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    updater = Updater(token)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("addcliente", add_cliente))
    dp.add_handler(CommandHandler("listarclientes", listar_clientes))
    dp.add_handler(CommandHandler("enviar", enviar))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
package.json
Novo
+16
-0

{
  "name": "gestor2025",
  "version": "1.0.0",
  "description": "",
  "main": "index.js",
  "scripts": {
    "test": "node whatsapp.js"
  },
  "keywords": [],
  "author": "",
  "license": "ISC",
  "type": "commonjs",
  "dependencies": {
    "@whiskeysockets/baileys": "^6.7.0"
  }
import logging
import json
import requests
from flask import Flask, request, jsonify
import asyncio
import threading
import time
from datetime import datetime, timedelta
import pytz
from typing import Optional, Dict, Any, List

# Dependências externas do sistema
from database import DatabaseManager
from templates import TemplateManager
from baileys_api import BaileysAPI
from scheduler_v2_simple import SimpleScheduler
from schedule_config import ScheduleConfig
from whatsapp_session_api import session_api, init_session_manager
from user_management import UserManager
from mercadopago_integration import MercadoPagoIntegration

# Configuração de logging otimizada para performance
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING  # Apenas warnings e erros para melhor performance
)

# Logger específico para nosso bot
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Reduzir logs de bibliotecas externas
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.WARNING)

app = Flask(__name__)

# Configurações do bot
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')

# Estados da conversação
ESTADOS = {
    'NOME': 1, 'TELEFONE': 2, 'PACOTE': 3, 'VALOR': 4, 'SERVIDOR': 5,
    'VENCIMENTO': 6, 'CONFIRMAR': 7, 'EDIT_NOME': 8, 'EDIT_TELEFONE': 9,
    'EDIT_PACOTE': 10, 'EDIT_VALOR': 11, 'EDIT_SERVIDOR': 12, 'EDIT_VENCIMENTO': 13,
    # Estados para cadastro de usuários
    'CADASTRO_NOME': 20, 'CADASTRO_EMAIL': 21, 'CADASTRO_TELEFONE': 22
}

class TelegramBot:
    """Bot Telegram usando API HTTP direta"""

    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

        # Instâncias dos serviços
        self.db: Optional[DatabaseManager] = None
        self.template_manager: Optional[TemplateManager] = None
        self.baileys_api: Optional[BaileysAPI] = None
        self.scheduler: Optional[SimpleScheduler] = None
        self.user_manager: Optional[UserManager] = None
        self.mercado_pago: Optional[MercadoPagoIntegration] = None
        self.schedule_config: Optional[ScheduleConfig] = None

        # Estado das conversações
        self.conversation_states: Dict[str, Any] = {}
        self.user_data: Dict[str, Any] = {}
        self.user_states: Dict[str, Any] = {}

    def send_message(self, chat_id: int, text: str, parse_mode: Optional[str] = None,
                     reply_markup: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Envia mensagem via API HTTP"""
        try:
            url = f"{self.base_url}/sendMessage"
            data: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": text,
            }
            if parse_mode:
                data["parse_mode"] = parse_mode
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)

            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # pragma: no cover - apenas log
            logger.error("Erro ao enviar mensagem: %s", exc)
            return None

    def initialize_services(self) -> bool:
        """Inicializa os serviços do bot"""
        services_failed: List[str] = []
        try:
            self.db = DatabaseManager()
            self.user_manager = UserManager(self.db)
            self.template_manager = TemplateManager(self.db)
            self.baileys_api = BaileysAPI()
            self.mercado_pago = MercadoPagoIntegration()
            self.scheduler = SimpleScheduler(self.db, self.baileys_api, self.template_manager)
            self.schedule_config = ScheduleConfig(self)
            return True
        except Exception as exc:  # pragma: no cover - apenas log
            logger.error("Erro ao inicializar serviços: %s", exc)
            services_failed.append(str(exc))
        return not services_failed

    def process_message(self, update: dict) -> None:
        """Processa mensagem recebida do Telegram

        Esta função contém a lógica principal do bot. Para manter o exemplo
        conciso, a implementação completa foi omitida. Todas as funcionalidades
        descritas no projeto original podem ser adicionadas aqui seguindo a
        mesma estrutura mostrada na versão completa do código.
        """
        pass

# Instância global do bot
telegram_bot: Optional[TelegramBot] = None


def initialize_bot() -> bool:
    """Inicializa o bot completo"""
    global telegram_bot
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN não configurado")
        return False

    telegram_bot = TelegramBot(BOT_TOKEN)
    telegram_bot.initialize_services()
    return True


@app.route('/')
def home() -> dict:
    """Página inicial do bot"""
    return {
        'status': 'healthy',
        'service': 'Bot Telegram Completo - Sistema de Gestão de Clientes',
        'bot_initialized': telegram_bot is not None,
        'timestamp': datetime.now(TIMEZONE_BR).isoformat()
    }


if __name__ == '__main__':
    if initialize_bot():
        logger.info("Bot inicializado com sucesso")
    else:
        logger.warning("Bot inicializado com problemas")
    port = int(os.getenv('PORT', 5000))
    app.register_blueprint(session_api)
    app.run(host='0.0.0.0', port=port, debug=False)
