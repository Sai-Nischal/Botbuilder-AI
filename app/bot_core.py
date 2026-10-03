from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session

from app.config import TELEGRAM_BOT_TOKEN, HIGH_THRESHOLD, LOW_THRESHOLD, PASSAGE_THRESHOLD
from app.db import Business, Bot, ChatMapping
from app.security import decrypt_bot_token
from app.matcher import query_business_index
from app.telegram_api import send_message, answer_callback_query


def build_menu_keyboard(faqs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates inline keyboard layout with up to 8 FAQ buttons (show_as_button == True)."""
    buttons = []
    button_faqs = [f for f in faqs if f.get("show_as_button", True)][:8]
    
    row = []
    for faq in button_faqs:
        label = faq.get("button_label") or faq.get("q", "")[:20]
        faq_id = faq.get("id")
        row.append({"text": label, "callback_data": f"faq:{faq_id}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    return {"inline_keyboard": buttons}


def build_menu_footer_keyboard() -> Dict[str, Any]:
    """Returns a single 'Main Menu' button footer."""
    return {
        "inline_keyboard": [[
            {"text": "📋 Main Menu", "callback_data": "cmd:menu"}
        ]]
    }


async def process_telegram_update(db: Session, update: Dict[str, Any], bot_key: Optional[str] = None) -> bool:
    """
    Unified Telegram update handler for both shared and branded bots.
    Resolves the target business, runs reply logic, and sends Telegram messages.
    """
    message = update.get("message")
    callback_query = update.get("callback_query")

    chat_id = None
    user_text = None
    callback_data = None
    callback_id = None

    if message:
        chat_id = message.get("chat", {}).get("id")
        user_text = message.get("text", "").strip()
    elif callback_query:
        callback_id = callback_query.get("id")
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
        callback_data = callback_query.get("data", "").strip()

    if not chat_id:
        return False

    chat_id_str = str(chat_id)
    target_business: Optional[Business] = None
    active_bot_token: str = TELEGRAM_BOT_TOKEN

    # 1. Business Resolution Logic
    if bot_key:
        # Branded Bot: fixed to business owning this bot_key
        bot_rec = db.query(Bot).filter(Bot.bot_key == bot_key, Bot.is_active == True).first()
        if not bot_rec or not bot_rec.business:
            print(f"[BOT CORE] Branded bot_key '{bot_key}' not found or inactive.")
            return False
        target_business = bot_rec.business
        if bot_rec.encrypted_token:
            active_bot_token = decrypt_bot_token(bot_rec.encrypted_token) or TELEGRAM_BOT_TOKEN
    else:
        # Shared Bot
        bot_id_tag = "shared"

        # Check if /start with deep link parameter: e.g. "/start sunrise-dental-a1b2"
        if user_text and user_text.startswith("/start"):
            parts = user_text.split(maxsplit=1)
            if len(parts) > 1:
                start_param = parts[1].strip()
                biz = db.query(Business).filter(Business.business_id == start_param).first()
                if biz:
                    target_business = biz
                    # Save chat mapping
                    existing_map = db.query(ChatMapping).filter(
                        ChatMapping.bot_id == bot_id_tag,
                        ChatMapping.chat_id == chat_id_str
                    ).first()
                    if existing_map:
                        existing_map.business_id = biz.business_id
                    else:
                        new_map = ChatMapping(
                            bot_id=bot_id_tag,
                            chat_id=chat_id_str,
                            business_id=biz.business_id
                        )
                        db.add(new_map)
                    db.commit()
                else:
                    # Invalid business ID parameter
                    await send_message(
                        active_bot_token,
                        chat_id,
                        "❌ Invalid business link. Please make sure you used the complete chatbot link."
                    )
                    return True

        if not target_business:
            # Resolve from existing ChatMapping
            mapping = db.query(ChatMapping).filter(
                ChatMapping.bot_id == bot_id_tag,
                ChatMapping.chat_id == chat_id_str
            ).first()
            if mapping:
                target_business = db.query(Business).filter(Business.business_id == mapping.business_id).first()

    # If business could not be identified
    if not target_business:
        await send_message(
            active_bot_token,
            chat_id,
            "👋 Welcome! To start chatting with a business bot, please open the unique link provided by the business."
        )
        return True

    cfg = target_business.get_config_dict()
    faqs = cfg.get("faqs", [])
    welcome_msg = cfg.get("welcome_message") or f"Welcome to {target_business.name}! How can we help you today?"
    contact_info = cfg.get("contact", {})
    phone = contact_info.get("phone", "")
    email = contact_info.get("email", "")
    contact_str = f" Phone: {phone}" if phone else ""
    if email:
        contact_str += f" Email: {email}"
    
    fallback_msg = cfg.get("fallback_message") or f"I couldn't find an answer to that. Please contact us directly.{contact_str}"

    menu_keyboard = build_menu_keyboard(faqs)

    # 2. Callback Query Handling
    if callback_query and callback_data:
        if callback_data.startswith("faq:"):
            try:
                faq_id = int(callback_data.split(":")[1])
                target_faq = next((f for f in faqs if f.get("id") == faq_id), None)
                await answer_callback_query(active_bot_token, callback_id)
                if target_faq:
                    await send_message(
                        active_bot_token,
                        chat_id,
                        target_faq.get("a", ""),
                        reply_markup=build_menu_footer_keyboard()
                    )
                else:
                    await send_message(active_bot_token, chat_id, "Answer not found.", reply_markup=menu_keyboard)
            except Exception as e:
                await answer_callback_query(active_bot_token, callback_id)
                await send_message(active_bot_token, chat_id, "Error processing selection.", reply_markup=menu_keyboard)
            return True

        elif callback_data == "cmd:menu":
            await answer_callback_query(active_bot_token, callback_id)
            await send_message(active_bot_token, chat_id, welcome_msg, reply_markup=menu_keyboard)
            return True

    # 3. Command Handling
    if user_text:
        if user_text.startswith("/start"):
            await send_message(active_bot_token, chat_id, welcome_msg, reply_markup=menu_keyboard)
            return True

        elif user_text in ("/menu", "/help"):
            await send_message(active_bot_token, chat_id, welcome_msg, reply_markup=menu_keyboard)
            return True

        elif user_text == "/contact":
            addr = contact_info.get("address", "")
            web = contact_info.get("website", "")
            info_text = f"📞 <b>Contact {target_business.name}</b>\n\n"
            if phone:
                info_text += f"• Phone: {phone}\n"
            if email:
                info_text += f"• Email: {email}\n"
            if addr:
                info_text += f"• Address: {addr}\n"
            if web:
                info_text += f"• Website: {web}\n"
            await send_message(active_bot_token, chat_id, info_text, reply_markup=build_menu_footer_keyboard())
            return True

        # 4. Typed Text Vector Matching Logic
        match_result = query_business_index(target_business.business_id, user_text)
        best_faq = match_result.get("best_faq")
        top_faqs = match_result.get("top_faqs", [])
        best_passage = match_result.get("best_passage")

        best_faq_score = best_faq["score"] if best_faq else 0.0

        # Case A: best_score >= HIGH_THRESHOLD (0.60)
        if best_faq and best_faq_score >= HIGH_THRESHOLD:
            faq_obj = next((f for f in faqs if f.get("id") == best_faq["faq_id"]), None)
            answer_text = faq_obj.get("a", "") if faq_obj else best_faq["text"]
            await send_message(active_bot_token, chat_id, answer_text, reply_markup=build_menu_footer_keyboard())
            return True

        # Case B: LOW_THRESHOLD (0.40) <= best_score < HIGH_THRESHOLD (0.60)
        elif best_faq and best_faq_score >= LOW_THRESHOLD:
            did_you_mean_buttons = []
            for item in top_faqs:
                f_obj = next((f for f in faqs if f.get("id") == item["faq_id"]), None)
                if f_obj:
                    label = f_obj.get("button_label") or f_obj.get("q")[:25]
                    did_you_mean_buttons.append([{"text": f"❓ {label}", "callback_data": f"faq:{f_obj.get('id')}"}])
            
            did_you_mean_buttons.append([{"text": "📋 View Main Menu", "callback_data": "cmd:menu"}])
            keyboard = {"inline_keyboard": did_you_mean_buttons}

            await send_message(
                active_bot_token,
                chat_id,
                "Did you mean one of these questions?",
                reply_markup=keyboard
            )
            return True

        # Case C: Check PDF Passage Fallback (PASSAGE_THRESHOLD >= 0.50)
        elif best_passage and best_passage["score"] >= PASSAGE_THRESHOLD:
            passage_text = best_passage["content"]
            response_text = f"📄 <i>Here's what I found from company documents:</i>\n\n{passage_text}"
            await send_message(active_bot_token, chat_id, response_text, reply_markup=build_menu_footer_keyboard())
            return True

        # Case D: Below LOW_THRESHOLD -> Send fallback message + Main Menu buttons
        else:
            await send_message(active_bot_token, chat_id, fallback_msg, reply_markup=menu_keyboard)
            return True

    return True
