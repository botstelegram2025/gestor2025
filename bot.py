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
    """Uso: /addcliente Nome Telefone Pacote"""
    session = Session()
    if len(context.args) < 3:
        update.message.reply_text("Uso: /addcliente Nome Telefone Pacote")
        return

    nome = context.args[0]
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
