import telebot
from telebot import types
import json
import os
import sys
from datetime import datetime
import schedule
import time
import threading
import random
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Adicionar o diretório pai ao path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar configurações
from config.config import TOKEN, ADMIN_ID, MAX_PARTNERS_PER_LIST, SCHEDULE_INTERVAL_HOURS

# Inicializar o bot
bot = telebot.TeleBot(TOKEN)

# Caminho para o arquivo de dados
DATA_FILE = os.path.join("data", "bot_data.json")

# Carregar dados do arquivo JSON
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    else:
        return {
            "admin_ids": [ADMIN_ID],
            "pending_registrations": [],
            "approved_partners": [],
            "protected_users": [],
            "settings": {
                "schedule_interval_hours": SCHEDULE_INTERVAL_HOURS,
                "max_partners_per_list": MAX_PARTNERS_PER_LIST
            },
            "admin_privileged_channels": []
        }

# Salvar dados no arquivo JSON
def save_data(data):
    if os.path.exists(DATA_FILE):
        # Criar um backup antes de salvar
        backup_file = DATA_FILE + ".bak"
        try:
            os.replace(DATA_FILE, backup_file)
        except OSError as e:
            print("Erro ao criar backup do arquivo de dados: {}".format(e))
    
    # Criar diretório se não existir
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Inicializar dados
data = load_data()

# Função para verificar se o usuário é administrador do bot
def is_admin(user_id):
    return user_id in data["admin_ids"]

# --- FUNCIONALIDADES PARA USUÁRIOS COMUNS ---

@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    if user_id not in [user["id"] for user in data["protected_users"]]:
        data["protected_users"].append({
            "id": user_id, 
            "username": message.from_user.username, 
            "first_name": message.from_user.first_name, 
            "last_name": message.from_user.last_name
        })
        save_data(data)

    if is_admin(user_id):
        show_admin_panel(message)
    else:
        show_user_menu(message)

def show_user_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=2)
    btn1 = types.KeyboardButton("🔍 Buscar Canais")
    btn2 = types.KeyboardButton("📁 Meus Canais")
    btn3 = types.KeyboardButton("👥 Meus Grupos")
    btn4 = types.KeyboardButton("⭐ Canais em Destaque")
    btn5 = types.KeyboardButton("➕ Adicionar Chat")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    bot.send_message(message.chat.id, "Bem-vindo! Escolha uma opção:", reply_markup=markup)

def show_admin_panel(message):
    markup = types.ReplyKeyboardMarkup(row_width=2)
    btn1 = types.KeyboardButton("⏳ Moderar Registros")
    btn2 = types.KeyboardButton("👥 Ver Rede")
    btn3 = types.KeyboardButton("🛡️ Usuários Protegidos")
    btn4 = types.KeyboardButton("📢 Enviar Listas")
    markup.add(btn1, btn2, btn3, btn4)
    bot.send_message(message.chat.id, "Painel Administrativo:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "➕ Adicionar Chat")
def add_chat(message):
    markup = types.InlineKeyboardMarkup()
    bot_username = bot.get_me().username
    btn1 = types.InlineKeyboardButton("👥 Adicionar Grupo", url="https://t.me/{}?startgroup=true".format(bot_username))
    btn2 = types.InlineKeyboardButton("📺 Adicionar Canal", url="https://t.me/{}?startchannel=true".format(bot_username))
    markup.add(btn1, btn2)
    bot.send_message(message.chat.id, "Onde você quer me adicionar?", reply_markup=markup)

@bot.message_handler(content_types=["group_chat_created", "supergroup_chat_created"])
def group_created(message):
    bot.send_message(message.chat.id, "Fui adicionado a um novo grupo! Para concluir o registro, por favor, encaminhe uma mensagem deste grupo para mim no privado.")

@bot.message_handler(func=lambda message: message.forward_from_chat is not None)
def handle_forwarded_message(message):
    chat_info = message.forward_from_chat
    user_id = message.from_user.id
    
    # Verificar se o chat já está registrado
    existing_reg = next((reg for reg in data["pending_registrations"] + data["approved_partners"] if reg["id"] == chat_info.id), None)
    if existing_reg:
        bot.send_message(message.chat.id, "Este chat já está registrado em nosso sistema.")
        return
    
    # Determinar o tipo de chat
    chat_type = "channel" if chat_info.type == "channel" else "group"
    
    # Criar registro pendente
    registration = {
        "id": chat_info.id,
        "title": chat_info.title,
        "type": chat_type,
        "registrant_id": user_id,
        "registrant_username": message.from_user.username,
        "registration_date": datetime.now().isoformat()
    }
    
    data["pending_registrations"].append(registration)
    save_data(data)
    
    bot.send_message(message.chat.id, "Registro enviado para aprovação! Você será notificado quando for aprovado.")

@bot.message_handler(func=lambda message: message.text == "📁 Meus Canais")
def my_channels(message):
    user_id = message.from_user.id
    user_channels = [p for p in data["approved_partners"] if p["registrant_id"] == user_id and p["type"] == "channel"]
    pending_channels = [p for p in data["pending_registrations"] if p["registrant_id"] == user_id and p["type"] == "channel"]

    if not user_channels and not pending_channels:
        bot.send_message(message.chat.id, "Você ainda não tem canais registrados.")
        return

    response = "Seus Canais:\n\n"
    for channel in user_channels:
        response += "✅ {} (Ativo)\n".format(channel["title"])
    for channel in pending_channels:
        response += "⏳ {} (Aguardando aprovação)\n".format(channel["title"])
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == "👥 Meus Grupos")
def my_groups(message):
    user_id = message.from_user.id
    user_groups = [p for p in data["approved_partners"] if p["registrant_id"] == user_id and p["type"] == "group"]
    pending_groups = [p for p in data["pending_registrations"] if p["registrant_id"] == user_id and p["type"] == "group"]

    if not user_groups and not pending_groups:
        bot.send_message(message.chat.id, "Você ainda não tem grupos registrados.")
        return

    response = "Seus Grupos:\n\n"
    for group in user_groups:
        response += "✅ {} (Ativo)\n".format(group["title"])
    for group in pending_groups:
        response += "⏳ {} (Aguardando aprovação)\n".format(group["title"])
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == "🔍 Buscar Canais")
def search_channels(message):
    approved_channels = [p for p in data["approved_partners"] if p["type"] == "channel"]
    if not approved_channels:
        bot.send_message(message.chat.id, "Nenhum canal aprovado encontrado no momento.")
        return

    response = "Canais Aprovados:\n\n"
    for channel in approved_channels:
        try:
            invite_link = bot.export_chat_invite_link(channel["id"])
            response += "📺 {} - {}\n".format(channel["title"], invite_link)
        except Exception as e:
            logging.error("Erro ao obter link de convite para {} ({}): {}".format(channel["title"], channel["id"], e))
            response += "📺 {} (Link indisponível)\n".format(channel["title"])
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == "⭐ Canais em Destaque")
def featured_channels(message):
    approved_channels = [p for p in data["approved_partners"] if p["type"] == "channel"]
    if not approved_channels:
        bot.send_message(message.chat.id, "Nenhum canal em destaque no momento.")
        return

    # Seleciona até 5 canais aleatoriamente para destaque
    featured = random.sample(approved_channels, min(len(approved_channels), 5))

    response = "Canais em Destaque:\n\n"
    for channel in featured:
        try:
            invite_link = bot.export_chat_invite_link(channel["id"])
            response += "⭐ {} - {}\n".format(channel["title"], invite_link)
        except Exception as e:
            logging.error("Erro ao obter link de convite para {} ({}): {}".format(channel["title"], channel["id"], e))
            response += "⭐ {} (Link indisponível)\n".format(channel["title"])
    bot.send_message(message.chat.id, response)

# --- FUNCIONALIDADES ADMINISTRATIVAS ---

@bot.message_handler(func=lambda message: message.text == "⏳ Moderar Registros" and is_admin(message.from_user.id))
def moderate_registrations(message):
    pending = data["pending_registrations"]
    if not pending:
        bot.send_message(message.chat.id, "Não há registros pendentes.")
        return

    for reg in pending:
        markup = types.InlineKeyboardMarkup()
        approve_button = types.InlineKeyboardButton("✅ Aprovar", callback_data="approve_{}".format(reg["id"]))
        reject_button = types.InlineKeyboardButton("❌ Rejeitar", callback_data="reject_{}".format(reg["id"]))
        markup.add(approve_button, reject_button)
        
        reg_text = "Novo Registro:\n\nNome: {}\nTipo: {}\nRegistrado por: @{}".format(
            reg["title"], 
            reg["type"], 
            reg["registrant_username"] or "N/A"
        )
        bot.send_message(message.chat.id, reg_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("reject_"))
def handle_moderation_callback(call):
    action, chat_id_str = call.data.split("_")
    chat_id = int(chat_id_str)

    pending_reg = next((reg for reg in data["pending_registrations"] if reg["id"] == chat_id), None)
    if not pending_reg:
        bot.answer_callback_query(call.id, "Registro não encontrado.")
        return

    if action == "approve":
        data["approved_partners"].append(pending_reg)
        approval_msg = "🎉 Parabéns! Seu {} '{}' foi aprovado e agora faz parte da nossa rede!".format(
            pending_reg["type"], 
            pending_reg["title"]
        )
        bot.send_message(pending_reg["registrant_id"], approval_msg)
        bot.edit_message_text("✅ Registro de '{}' aprovado.".format(pending_reg["title"]), call.message.chat.id, call.message.message_id)
    else:
        rejection_msg = "😔 Infelizmente, seu {} '{}' não foi aprovado.".format(
            pending_reg["type"], 
            pending_reg["title"]
        )
        bot.send_message(pending_reg["registrant_id"], rejection_msg)
        bot.edit_message_text("❌ Registro de '{}' rejeitado.".format(pending_reg["title"]), call.message.chat.id, call.message.message_id)
    
    data["pending_registrations"] = [reg for reg in data["pending_registrations"] if reg["id"] != chat_id]
    save_data(data)
    bot.answer_callback_query(call.id, "Ação concluída.")

@bot.message_handler(func=lambda message: message.text == "👥 Ver Rede" and is_admin(message.from_user.id))
def view_network(message):
    approved_groups = [p for p in data["approved_partners"] if p["type"] == "group"]
    approved_channels = [p for p in data["approved_partners"] if p["type"] == "channel"]

    response = "**Rede de Parceiros:**\n\n"
    response += "**Total de Parceiros Aprovados:** {}\n".format(len(data["approved_partners"]))
    response += "**Grupos Aprovados:** {}\n".format(len(approved_groups))
    response += "**Canais Aprovados:** {}\n\n".format(len(approved_channels))

    if approved_groups:
        response += "**Lista de Grupos Aprovados:**\n"
        for group in approved_groups:
            response += "- {}\n".format(group["title"])
        response += "\n"

    if approved_channels:
        response += "**Lista de Canais Aprovados:**\n"
        for channel in approved_channels:
            response += "- {}\n".format(channel["title"])
        response += "\n"

    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🛡️ Usuários Protegidos" and is_admin(message.from_user.id))
def protected_users(message):
    protected = data["protected_users"]
    if not protected:
        bot.send_message(message.chat.id, "Nenhum usuário protegido encontrado.")
        return

    response = "**Usuários Protegidos:**\n\n"
    response += "**Total de Usuários:** {}\n\n".format(len(protected))

    for user in protected:
        username = "@{}".format(user['username']) if user['username'] else "N/A"
        last_name = user.get('last_name', '') or ''
        response += "- ID: {}, Nome: {} {}, Username: {}\n".format(
            user['id'], 
            user['first_name'], 
            last_name, 
            username
        )

    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📢 Enviar Listas" and is_admin(message.from_user.id))
def send_lists_manual(message):
    bot.send_message(message.chat.id, "Processando e enviando listas de divulgação. Isso pode levar alguns minutos...")
    create_and_send_lists()
    bot.send_message(message.chat.id, "Listas de divulgação enviadas com sucesso!")

# Função para criar e enviar listas de divulgação
def create_and_send_lists():
    try:
        approved_partners = data["approved_partners"]
        if not approved_partners:
            logging.info("Nenhum parceiro aprovado para enviar listas.")
            return

        # Dividir parceiros em listas menores
        max_per_list = data["settings"]["max_partners_per_list"]
        partner_lists = [approved_partners[i:i + max_per_list] for i in range(0, len(approved_partners), max_per_list)]

        for i, partner_list in enumerate(partner_lists):
            list_message = "📢 **Lista de Divulgação {}**\n\n".format(i + 1)
            
            for partner in partner_list:
                try:
                    invite_link = bot.export_chat_invite_link(partner["id"])
                    emoji = "📺" if partner["type"] == "channel" else "👥"
                    list_message += "{} {} - {}\n".format(emoji, partner["title"], invite_link)
                except Exception as e:
                    logging.error("Erro ao obter link para {}: {}".format(partner["title"], e))
                    emoji = "📺" if partner["type"] == "channel" else "👥"
                    list_message += "{} {} (Link indisponível)\n".format(emoji, partner["title"])

            # Enviar para todos os parceiros aprovados
            for partner in approved_partners:
                try:
                    bot.send_message(partner["id"], list_message, parse_mode="Markdown")
                    time.sleep(1)  # Evitar spam
                except Exception as e:
                    logging.error("Erro ao enviar lista para {}: {}".format(partner["title"], e))

        logging.info("Listas de divulgação enviadas com sucesso!")
        
    except Exception as e:
        logging.error("Erro ao criar e enviar listas: {}".format(e))

# Função para executar o agendador
def run_scheduler():
    schedule.every(data["settings"]["schedule_interval_hours"]).hours.do(create_and_send_lists)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # Iniciar o agendador em uma thread separada
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    # Iniciar o bot
    print("Bot em execução...")
    bot.polling()

