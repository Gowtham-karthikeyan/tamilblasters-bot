import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    CallbackContext, CallbackQueryHandler, ConversationHandler
)
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import time
from datetime import datetime

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot states for conversation handler
SEARCHING, CATEGORY = range(2)

# Configuration
TOKEN = "7359247062:AAFqVZTq3ue1YpoyhmsHLQidYwfcjcwQm1I"
REQUEST_DELAY = 2  # seconds between requests to avoid being blocked
MAX_RESULTS = 10
CACHE_TIME = 1800  # 30 minutes in seconds

# TamilBlasters configuration (example - verify actual structure)
BASE_URL = "https://www.1tamilblasters.earth/"
SEARCH_URL = BASE_URL + "search?query="
CATEGORIES = {
    'movies': '/movies',
    'tv': '/tv-shows',
    'music': '/music',
    'games': '/games',
    'anime': '/anime'
}

class TamilBlastersScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.last_request_time = 0
        
    def _rate_limit(self):
        """Ensure we don't send requests too quickly"""
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def search(self, query, category=None):
        """Search TamilBlasters for torrents"""
        try:
            self._rate_limit()
            
            # Construct search URL
            search_url = SEARCH_URL + quote(query)
            if category and category in CATEGORIES:
                search_url += CATEGORIES[category]
            
            response = self.session.get(search_url)
            response.raise_for_status()
            
            return self._parse_results(response.text)
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return None
    
    def _parse_results(self, html):
        """Parse HTML results from TamilBlasters"""
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
        # This needs to be adapted to TamilBlasters' actual HTML structure
        torrent_items = soup.select('.torrent-list .torrent-item')  
        
        for item in torrent_items[:MAX_RESULTS]:
            try:
                title_elem = item.select_one('.torrent-title')
                title = title_elem.text.strip() if title_elem else "No title"
                
                magnet = item.select_one('[href^="magnet:"]')['href'] if item.select_one('[href^="magnet:"]') else None
                
                # Additional metadata
                size = item.select_one('.torrent-size').text.strip() if item.select_one('.torrent-size') else "N/A"
                seeds = item.select_one('.torrent-seeds').text.strip() if item.select_one('.torrent-seeds') else "0"
                date = item.select_one('.torrent-date').text.strip() if item.select_one('.torrent-date') else "N/A"
                
                results.append({
                    'title': title,
                    'magnet': magnet,
                    'size': size,
                    'seeds': seeds,
                    'date': date
                })
            except Exception as e:
                logger.warning(f"Error parsing torrent item: {e}")
                continue
                
        return results

# Initialize scraper
scraper = TamilBlastersScraper()

def start(update: Update, context: CallbackContext) -> None:
    """Send welcome message and instructions"""
    user = update.effective_user
    welcome_msg = (
        f"👋 Hello {user.first_name}!\n\n"
        "I can help you search for torrents on TamilBlasters.\n\n"
        "🔍 You can:\n"
        "- Send me a search query directly\n"
        "- Use /search to start an interactive search\n"
        "- Use /categories to browse by category\n\n"
        "⚠️ Note: Always comply with your local laws."
    )
    
    update.message.reply_text(welcome_msg)

def search_command(update: Update, context: CallbackContext) -> int:
    """Start interactive search conversation"""
    update.message.reply_text(
        "🔍 What would you like to search for?\n"
        "(You can also specify a category like 'movies: vikram')"
    )
    return SEARCHING

def search_category(update: Update, context: CallbackContext) -> None:
    """Show available categories"""
    keyboard = [
        [InlineKeyboardButton(cat.capitalize(), callback_data=f"cat_{cat}")]
        for cat in CATEGORIES.keys()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "📚 Select a category to browse:",
        reply_markup=reply_markup
    )

def handle_category_selection(update: Update, context: CallbackContext) -> None:
    """Handle category selection callback"""
    query = update.callback_query
    query.answer()
    
    category = query.data.split('_')[1]
    context.user_data['category'] = category
    
    query.edit_message_text(
        text=f"Selected category: {category.capitalize()}\n\n"
             "Now send me your search query for this category:"
    )
    return SEARCHING

def perform_search(update: Update, context: CallbackContext) -> int:
    """Perform the actual search"""
    query = update.message.text
    user_data = context.user_data
    
    # Check if we're in a category search
    category = user_data.get('category')
    
    # Check if query contains category prefix (e.g., "movies: vikram")
    if not category and ':' in query:
        parts = query.split(':', 1)
        possible_cat = parts[0].strip().lower()
        if possible_cat in CATEGORIES:
            category = possible_cat
            query = parts[1].strip()
    
    if not query:
        update.message.reply_text("Please provide a search term.")
        return SEARCHING
    
    update.message.reply_text(f"🔍 Searching for '{query}'{' in ' + category if category else ''}...")
    
    results = scraper.search(query, category)
    
    if not results:
        update.message.reply_text("❌ No results found or there was an error searching.")
        return ConversationHandler.END
    
    # Clear category after search
    if 'category' in user_data:
        del user_data['category']
    
    # Send results
    for result in results:
        keyboard = []
        if result['magnet']:
            keyboard.append([InlineKeyboardButton("🧲 Magnet Link", url=result['magnet'])])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        message = (
            f"🎬 <b>{result['title']}</b>\n"
            f"📦 Size: {result['size']}\n"
            f"🌱 Seeds: {result['seeds']}\n"
            f"📅 Date: {result['date']}"
        )
        
        update.message.reply_text(
            message, 
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    update.message.reply_text(
        f"✅ Found {len(results)} results\n"
        "You can search again or use /categories to browse by category."
    )
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the current operation"""
    update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

def error_handler(update: Update, context: CallbackContext) -> None:
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error {context.error}")
    if update.message:
        update.message.reply_text("❌ An error occurred. Please try again later.")

def main() -> None:
    """Start the bot."""
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Conversation handler for interactive search
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('search', search_command)],
        states={
            SEARCHING: [
                MessageHandler(Filters.text & ~Filters.command, perform_search),
                CommandHandler('cancel', cancel)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Register handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("categories", search_category))
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CallbackQueryHandler(handle_category_selection, pattern=r'^cat_'))
    
    # Handle direct search queries (not in conversation)
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, perform_search))
    
    # Register error handler
    dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()
    logger.info("Bot started and running...")
    updater.idle()

if __name__ == '__main__':
    main()