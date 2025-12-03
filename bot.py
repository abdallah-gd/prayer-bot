import logging
import requests
from datetime import datetime, timedelta
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import json
import os
import time

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TON_TOKEN_ICI")  # Lit depuis variables d'environnement
LATITUDE = 36.75  # Harrach, Alger
LONGITUDE = 3.04
METHOD = 18  # Algeria method
TIMEZONE = pytz.timezone('Africa/Algiers')

# Fichier pour sauvegarder les utilisateurs
USERS_FILE = "users.json"

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Crée le bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)


class PrayerBot:
    def __init__(self):
        self.users = self.load_users()
        self.sent_reminders = {}  # Pour éviter les doublons
        
    def load_users(self):
        """Charge les chat IDs des utilisateurs"""
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        return []
    
    def save_users(self):
        """Sauvegarde les chat IDs"""
        with open(USERS_FILE, 'w') as f:
            json.dump(self.users, f)
    
    def get_prayer_times(self):
        """Récupère les horaires de prière via API Aladhan"""
        try:
            today = datetime.now(TIMEZONE).strftime("%d-%m-%Y")
            url = f"http://api.aladhan.com/v1/timings/{today}"
            params = {
                'latitude': LATITUDE,
                'longitude': LONGITUDE,
                'method': METHOD
            }
            
            response = requests.get(url, params=params)
            data = response.json()
            
            if data['code'] == 200:
                timings = data['data']['timings']
                # Retourne uniquement les 5 prières principales
                prayers = {
                    'Fajr': timings['Fajr'],
                    'Dhuhr': timings['Dhuhr'],
                    'Asr': timings['Asr'],
                    'Maghrib': timings['Maghrib'],
                    'Isha': timings['Isha']
                }
                return prayers
            return None
        except Exception as e:
            logger.error(f"Erreur API: {e}")
            return None
    
    def send_reminder(self, prayer_name, prayer_time):
        """Envoie le rappel à tous les utilisateurs"""
        message = f"🕌 Rappel: La prière de {prayer_name} est dans 1 heure ({prayer_time})\n\nAllah Akbar!"
        
        for chat_id in self.users:
            try:
                bot.send_message(chat_id, message)
                logger.info(f"Rappel envoyé à {chat_id} pour {prayer_name}")
            except Exception as e:
                logger.error(f"Erreur envoi à {chat_id}: {e}")
    
    def check_prayer_times(self):
        """Vérifie si un rappel doit être envoyé"""
        prayers = self.get_prayer_times()
        if not prayers:
            return
        
        now = datetime.now(TIMEZONE)
        today_key = now.strftime("%Y-%m-%d")
        
        # Réinitialise les rappels envoyés si on change de jour
        if today_key not in self.sent_reminders:
            self.sent_reminders = {today_key: []}
        
        for prayer_name, prayer_time_str in prayers.items():
            # Parse l'heure de prière
            prayer_time = datetime.strptime(prayer_time_str, "%H:%M").replace(
                year=now.year,
                month=now.month,
                day=now.day,
                tzinfo=TIMEZONE
            )
            
            # Calcule 1h avant
            reminder_time = prayer_time - timedelta(hours=1)
            
            # Si on est dans la minute du rappel et pas encore envoyé
            time_diff = abs((now - reminder_time).total_seconds())
            reminder_key = f"{today_key}-{prayer_name}"
            
            if time_diff < 60 and reminder_key not in self.sent_reminders[today_key]:
                logger.info(f"Envoi rappel pour {prayer_name}")
                self.send_reminder(prayer_name, prayer_time_str)
                self.sent_reminders[today_key].append(reminder_key)


# Instance globale
prayer_bot = PrayerBot()


# Commandes du bot
@bot.message_handler(commands=['start'])
def start(message):
    """Commande /start"""
    chat_id = message.chat.id
    
    if chat_id not in prayer_bot.users:
        prayer_bot.users.append(chat_id)
        prayer_bot.save_users()
    
    bot.reply_to(
        message,
        "🕌 Assalamu Alaikum!\n\n"
        "Je vais t'envoyer des rappels 1h avant chaque prière.\n\n"
        "Commandes disponibles:\n"
        "/today - Voir les horaires d'aujourd'hui\n"
        "/stop - Arrêter les rappels"
    )


@bot.message_handler(commands=['today'])
def today(message):
    """Commande /today - Affiche les horaires du jour"""
    prayers = prayer_bot.get_prayer_times()
    
    if prayers:
        response = "📅 Horaires de prière aujourd'hui (Harrach, Alger):\n\n"
        for name, time in prayers.items():
            response += f"🕌 {name}: {time}\n"
        response += "\n✅ Tu recevras un rappel 1h avant chaque prière"
    else:
        response = "❌ Impossible de récupérer les horaires. Réessaie plus tard."
    
    bot.reply_to(message, response)


@bot.message_handler(commands=['stop'])
def stop(message):
    """Commande /stop - Désactive les rappels"""
    chat_id = message.chat.id
    
    if chat_id in prayer_bot.users:
        prayer_bot.users.remove(chat_id)
        prayer_bot.save_users()
        bot.reply_to(message, "❌ Rappels désactivés. Utilise /start pour les réactiver.")
    else:
        bot.reply_to(message, "Tu n'es pas inscrit aux rappels.")


def main():
    """Lance le bot"""
    logger.info("🕌 Bot démarré! En attente de rappels...")
    
    # Configure le scheduler pour vérifier chaque minute
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        prayer_bot.check_prayer_times,
        'interval',
        minutes=1
    )
    scheduler.start()
    
    # Lance le bot en mode polling
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except KeyboardInterrupt:
        logger.info("Arrêt du bot...")
        scheduler.shutdown()


if __name__ == '__main__':
    main()