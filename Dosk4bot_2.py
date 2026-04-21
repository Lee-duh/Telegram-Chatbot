from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime

# =========================
# DATABASE SETUP
# =========================
# Create database file and table
conn = sqlite3.connect("reservations.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS reservations (
    user_id INTEGER,
    name TEXT,
    phone TEXT,
    date TEXT,
    time TEXT,
    people INTEGER,
    place TEXT,
    room_type INTEGER
)
""")
conn.commit()

# =========================
# MEMORY STORAGE (TEMP DATA)
# =========================
user_state = {}
reservation_data = {}

# =========================
# ROOM CONFIGURATION
# =========================
room_capacity = {
    6: 2,
    8: 2,
    10: 2
}

# =========================
# HELPER FUNCTIONS
# =========================

# Decide which room type fits the group
def get_room_type(people):
    if people >= 10:
        return 10
    elif people >= 8:
        return 8
    elif people >= 6:
        return 6
    return None

# Check if room is available
def is_room_available(date, time, room_type):
    cursor.execute(
        "SELECT COUNT(*) FROM reservations WHERE date=? AND time=? AND room_type=?",
        (date, time, room_type)
    )
    count = cursor.fetchone()[0]
    return count < room_capacity[room_type]

# Remove past reservations (simple auto-expire)
def remove_expired():
    now = datetime.now()
    cursor.execute("SELECT rowid, date, time FROM reservations")
    rows = cursor.fetchall()

    for row in rows:
        row_id, date_str, time_str = row
        try:
            dt = datetime.strptime(date_str + " " + time_str, "%B %d %H:%M")
            if dt < now:
                cursor.execute("DELETE FROM reservations WHERE rowid=?", (row_id,))
        except:
            pass

    conn.commit()

# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Type /reserve to make a reservation.")

# Start reservation process
async def reserve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    user_state[user_id] = "ASK_NAME"
    await update.message.reply_text("👤 What is your name?")

# =========================
# MAIN BOT LOGIC
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    text = update.message.text

    if user_id not in user_state:
        await update.message.reply_text("Type /reserve to start.")
        return

    # ASK NAME
    if user_state[user_id] == "ASK_NAME":
        reservation_data[user_id] = {"name": text}
        user_state[user_id] = "ASK_PHONE"
        await update.message.reply_text("📞 Enter your phone number:")

    # ASK PHONE
    elif user_state[user_id] == "ASK_PHONE":
        reservation_data[user_id]["phone"] = text
        user_state[user_id] = "ASK_DATE"
        await update.message.reply_text("📅 What date? (e.g., March 25)")

    # ASK DATE
    elif user_state[user_id] == "ASK_DATE":
        reservation_data[user_id]["date"] = text
        user_state[user_id] = "ASK_TIME"
        await update.message.reply_text(
            "⏰ Our restaurant open from 10am to 10pm. What time do you want? (HH:MM)"
        )

    # ASK TIME
    elif user_state[user_id] == "ASK_TIME":
        reservation_data[user_id]["time"] = text
        user_state[user_id] = "ASK_PLACE"

        keyboard = [["Room", "Outside"]]
        await update.message.reply_text(
            "📍 Do you want to book a room or outside?",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )

    # ASK PLACE
    elif user_state[user_id] == "ASK_PLACE":
        choice = text.lower()
        if choice not in ["room", "outside"]:
            await update.message.reply_text("❌ Choose Room or Outside.")
            return

        reservation_data[user_id]["place"] = choice
        user_state[user_id] = "ASK_PEOPLE"
        await update.message.reply_text("👥 How many people?")

    # ASK PEOPLE
    elif user_state[user_id] == "ASK_PEOPLE":
        if not text.isdigit():
            await update.message.reply_text("❌ Enter a valid number.")
            return

        people = int(text)
        data = reservation_data[user_id]
        data["people"] = people

        # ROOM LOGIC
        if data["place"] == "room":
            if people < 6:
                await update.message.reply_text("❌ Rooms are for 6+ people.")
                return

            room_type = get_room_type(people)

            if not is_room_available(data["date"], data["time"], room_type):
                await update.message.reply_text(
                    f"❌ {room_type}-person room is full."
                )
                user_state[user_id] = "ASK_TIME"
                return

            data["room_type"] = room_type
        else:
            data["room_type"] = None

        # CONFIRMATION
        keyboard = [["Yes", "No"]]
        await update.message.reply_text(
            f"✅ Confirm?\n\n"
            f"👤 {data['name']}\n"
            f"📞 {data['phone']}\n"
            f"📅 {data['date']}\n"
            f"⏰ {data['time']}\n"
            f"📍 {data['place']}\n"
            f"👥 {data['people']}",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )

        user_state[user_id] = "CONFIRM"

    # CONFIRM
    elif user_state[user_id] == "CONFIRM":
        if text.lower() == "yes":
            data = reservation_data[user_id]

            cursor.execute(
                "INSERT INTO reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    data["name"],
                    data["phone"],
                    data["date"],
                    data["time"],
                    data["people"],
                    data["place"],
                    data["room_type"]
                )
            )
            conn.commit()

            await update.message.reply_text("🎉 Reservation confirmed!")

        else:
            await update.message.reply_text("❌ Cancelled.")

        user_state[user_id] = "DONE"

# =========================
# CHECK RESERVATIONS (USER)
# =========================
async def my_reservation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id

    cursor.execute(
        "SELECT name, date, time, people, place FROM reservations WHERE user_id=?",
        (user_id,)
    )
    results = cursor.fetchall()

    if results:
        msg = "📋 Your Reservations:\n\n"
        for i, row in enumerate(results, start=1):
            msg += f"{i}. 👤 {row[0]} | 📅 {row[1]} | ⏰ {row[2]} | 👥 {row[3]} | 📍 {row[4]}\n"
    else:
        msg = "❌ No reservations found."

    await update.message.reply_text(msg)

# =========================
# CHECK BY NAME OR PHONE
# =========================
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)

    cursor.execute(
        "SELECT name, date, time, people, place FROM reservations WHERE name=? OR phone=?",
        (query, query)
    )
    results = cursor.fetchall()

    if results:
        msg = f"📋 Results for {query}:\n\n"
        for row in results:
            msg += f"👤 {row[0]} | 📅 {row[1]} | ⏰ {row[2]} | 👥 {row[3]} | 📍 {row[4]}\n"
    else:
        msg = "❌ No reservation found."

    await update.message.reply_text(msg)

# =========================
# CANCEL COMMAND
# =========================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    user_state[user_id] = "START"
    await update.message.reply_text("❌ Reservation cancelled.")

# =========================
# RUN BOT
# =========================
app = ApplicationBuilder().token("8687225011:AAEkSszuydSegspCwFTlELBhAa0zEoUMTPY").build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("reserve", reserve))
app.add_handler(CommandHandler("myreservation", my_reservation))
app.add_handler(CommandHandler("check", check))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot is running...")
remove_expired()  # clean old data on startup
app.run_polling()