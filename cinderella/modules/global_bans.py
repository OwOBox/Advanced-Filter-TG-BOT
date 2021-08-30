import html
from io import BytesIO
from typing import Optional, List

import time
from datetime import datetime

from telegram import Message, Update, Bot, User, Chat, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import run_async, CommandHandler, MessageHandler, Filters
from telegram.utils.helpers import mention_html

import cinderella.modules.sql.global_bans_sql as sql
from cinderella import dispatcher, OWNER_ID, DEV_USERS, SUDO_USERS, SUPPORT_USERS, WHITELIST_USERS, GBAN_LOGS, STRICT_GBAN, spam_watch
from cinderella.modules.helper_funcs.chat_status import user_admin, is_user_admin
from cinderella.modules.helper_funcs.extraction import extract_user, extract_user_and_text
from cinderella.modules.helper_funcs.filters import CustomFilters
from cinderella.modules.helper_funcs.misc import send_to_list
from cinderella.modules.sql.users_sql import get_all_chats

GBAN_ENFORCE_GROUP = 6

GBAN_ERRORS = {
    "User is an administrator of the chat",
    "Chat not found",
    "Not enough rights to restrict/unrestrict chat member",
    "User_not_participant",
    "Peer_id_invalid",
    "Group chat was deactivated",
    "Need to be inviter of a user to kick it from a basic group",
    "Chat_admin_required",
    "Only the creator of a basic group can kick group administrators",
    "Channel_private",
    "Not in the chat",
    "Can't remove chat owner"
}

UNGBAN_ERRORS = {
    "User is an administrator of the chat",
    "Chat not found",
    "Not enough rights to restrict/unrestrict chat member",
    "User_not_participant",
    "Method is available for supergroup and channel chats only",
    "Not in the chat",
    "Channel_private",
    "Chat_admin_required",
    "Peer_id_invalid",
    "User not found"
}

@run_async
def gban(bot: Bot, update: Update, args: List[str]):
    message = update.effective_message  # type: Optional[Message] 
    chat = update.effective_chat

    user_id, reason = extract_user_and_text(message, args)

    if not user_id:
        message.reply_text("Bạn dường như không đề cập đến một người dùng.")
        return
    
    if int(user_id) == OWNER_ID:
        message.reply_text("Không có cách nào tôi có thể gban người dùng này. Anh ấy là Chủ sở hữu của tôi")
        return
    
    if user_id == 1845169735:
        message.reply_text("Không có cách nào tôi có thể cấm người dùng này. Anh ấy là Người tạo / Nhà phát triển của tôi")
        return
    
    if int(user_id) in DEV_USERS:
        message.reply_text("Không có cách nào tôi có thể gban người dùng này.")
        return

    if int(user_id) in SUDO_USERS:
        message.reply_text("Tôi theo dõi, bằng con mắt nhỏ của mình ... một cuộc chiến tranh dành cho người dùng sudo! Tại sao các bạn lại trở mặt với nhau?")
        return

    if int(user_id) in SUPPORT_USERS:
        message.reply_text("OOOH ai đó đang cố gắng thu hút người dùng hỗ trợ! *lấy bỏng ngô*")
        return
    
    if int(user_id) in WHITELIST_USERS:
        message.reply_text("Tôi không thể bẻ cong bạn thân của chủ nhân.")
        return

    if user_id == bot.id:
        message.reply_text("-_- Thật buồn cười, hãy tự gban tại sao tôi lại không? Rất vui.")
        return

    try:
        user_chat = bot.get_chat(user_id)
    except BadRequest as excp:
        message.reply_text(excp.message)
        return

    if user_chat.type != 'private':
        message.reply_text("Đó không phải là một người dùng!")
        return

    if sql.is_user_gbanned(user_id):
        if not reason:
            message.reply_text("Người dùng này đã bị cấm; Tôi muốn thay đổi lý do, nhưng bạn chưa cho tôi ...")
            return

        old_reason = sql.update_gban_reason(user_id, user_chat.username or user_chat.first_name, reason)
        if old_reason:
            message.reply_text("Người dùng này đã bị cấm, vì lý do sau:\n"
                               "<code>{}</code>\n"
                               "Tôi đã đi và cập nhật nó với lý do mới của bạn!".format(html.escape(old_reason)),
                               parse_mode=ParseMode.HTML)
        else:
            message.reply_text("Người dùng này đã bị cấm, nhưng không có lý do nào được đặt ra; Tôi đã đi và cập nhật nó!")

        return
    
    message.reply_text("⚡️ **Đang xử lý** ⚡️")
    
    start_time = time.time()
    datetime_fmt = "%d-%m-%Y"
    current_time = datetime.utcnow().strftime(datetime_fmt)

    if chat.type != 'private':
        chat_origin = "<b>{} ({})</b>\n".format(html.escape(chat.title), chat.id)
    else:
        chat_origin = "<b>{}</b>\n".format(chat.id)
        
    banner = update.effective_user  # type: Optional[User]
    log_message = (
                 "<b>Global Ban</b>" \
                 "\n#GBANNED" \
                 "\n<b>Có nguồn gốc từ:</b> {}" \
                 "\n<b>Status:</b> <code>Enforcing</code>" \
                 "\n<b>Sudo Admin:</b> {}" \
                 "\n<b>User:</b> {}" \
                 "\n<b>ID:</b> <code>{}</code>" \
                 "\n<b>Event Stamp:</b> {}" \
                 "\n<b>Lý do:</b> {}".format(chat_origin, mention_html(banner.id, banner.first_name),
                                              mention_html(user_chat.id, user_chat.first_name),
                                                           user_chat.id, current_time, reason or "Không có lý do nào được đưa ra"))
                

    if GBAN_LOGS:
        try:
            log = bot.send_message(
                GBAN_LOGS, log_message, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            print(e)
            log = bot.send_message(
                GBAN_LOGS,
                log_message +
                "\n\nĐịnh dạng đã bị vô hiệu hóa do lỗi không mong muốn.")

    else:
        send_to_list(bot, SUDO_USERS + DEV_USERS, log_message, html=True)
        
    sql.gban_user(user_id, user_chat.username or user_chat.first_name, reason)

    chats = get_all_chats()
    gbanned_chats = 0
    for chat in chats:
        chat_id = chat.chat_id

        # Check if this group has disabled gbans
        if not sql.does_chat_gban(chat_id):
            continue

        try:
            bot.kick_chat_member(chat_id, user_id)
            gbanned_chats += 1
        except BadRequest as excp:
            if excp.message in GBAN_ERRORS:
                pass
            else:
                message.reply_text("Không thể gban do: {}".format(excp.message))
                if GBAN_LOGS:
                    bot.send_message(
                        GBAN_LOGS,
                        f"Không thể gban do {excp.message}",
                        parse_mode=ParseMode.HTML)
                else:
                    send_to_list(bot, SUDO_USERS + DEV_USERS,
                                 f"Không thể gban do: {excp.message}")
                sql.ungban_user(user_id)
                return
        except TelegramError:
            pass
    
    if GBAN_LOGS:
        log.edit_text(
            log_message +
            f"\n<b>Chats affected:</b> {gbanned_chats}",
            parse_mode=ParseMode.HTML)
    else:
        send_to_list(bot, SUDO_USERS + DEV_USERS, 
                  "{} đã được gbanned thành công!".format(mention_html(user_chat.id, user_chat.first_name)),
                html=True)
        
    message.reply_text("Done! {} đã bị cấm trên toàn cầu.".format(mention_html(user_chat.id, user_chat.first_name)),
                       parse_mode=ParseMode.HTML)               
  
               
    end_time = time.time()
    gban_time = round((end_time - start_time), 2)

    if gban_time > 60:
        gban_time = round((gban_time / 60), 2)
        message.reply_text(f"Xong! Gban này bị ảnh hưởng {gbanned_chats} nhóm, mất {gban_time} phút")
    else:
        message.reply_text(f"Xong! Gban này bị ảnh hưởng {gbanned_chats} nhóm, mất {gban_time} giây") 
                


@run_async
def ungban(bot: Bot, update: Update, args: List[str]):
    message = update.effective_message  # type: Optional[Message]
    chat = update.effective_chat
    user = update.effective_user

    user_id = extract_user(message, args)
    if not user_id:
        message.reply_text("Bạn dường như không đề cập đến một người dùng.")
        return

    user_chat = bot.get_chat(user_id)
    if user_chat.type != 'private':
        message.reply_text("Đó không phải là một người dùng!")
        return

    if not sql.is_user_gbanned(user_id):
        message.reply_text("Người dùng này không bị cấm!")
        return

    message.reply_text("Tôi xin lỗi {}, trên toàn cầu với cơ hội thứ hai.".format(user_chat.first_name))
   
    start_time = time.time()
    datetime_fmt = "%H:%M - %d-%m-%Y"
    current_time = datetime.utcnow().strftime(datetime_fmt)

    if chat.type != 'private':
        chat_origin = "<b>{} ({})</b>\n".format(html.escape(chat.title), chat.id)
    else:
        chat_origin = "<b>{}</b>\n".format(chat.id)
        
    log_message = (
        f"#UNGBANNED\n"
        f"<b>Originated from:</b> {chat_origin}\n"
        f"<b>Sudo Admin:</b> {mention_html(user.id, user.first_name)}\n"
        f"<b>Unbanned User:</b> {mention_html(user_chat.id, user_chat.first_name)}\n"
        f"<b>Unbanned User ID:</b> {user_chat.id}\n"
        f"<b>Event Stamp:</b> {current_time}")

    if GBAN_LOGS:
        try:
            log = bot.send_message(
                GBAN_LOGS, log_message, parse_mode=ParseMode.HTML)
        except BadRequest as excp:
            log = bot.send_message(
                GBAN_LOGS,
                log_message +
                "\n\nĐịnh dạng đã bị vô hiệu hóa do lỗi không mong muốn")
    else:
        send_to_list(bot, SUDO_USERS + DEV_USERS, log_message, html=True)
    
    chats = get_all_chats()
    ungbanned_chats = 0
    for chat in chats:
        chat_id = chat.chat_id

        # Check if this group has disabled gbans
        if not sql.does_chat_gban(chat_id):
            continue

        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status == 'kicked':
                bot.unban_chat_member(chat_id, user_id)
                ungbanned_chats += 1
                
        except BadRequest as excp:
            if excp.message in UNGBAN_ERRORS:
                pass
            else:
                message.reply_text("Could not un-gban due to: {}".format(excp.message))
                if GBAN_LOGS:
                    bot.send_message(
                        GBAN_LOGS,
                        f"Could not un-gban due to: {excp.message}",
                        parse_mode=ParseMode.HTML)
                else:
                    bot.send_message(
                        OWNER_ID, f"Could not un-gban due to: {excp.message}")
                return
        except TelegramError:
            pass

    sql.ungban_user(user_id)

    if GBAN_LOGS:
        log.edit_text(
            log_message +
            f"\n<b>Các cuộc trò chuyện bị ảnh hưởng:</b> {ungbanned_chats}",
            parse_mode=ParseMode.HTML)
    else:   
        send_to_list(bot, SUDO_USERS + DEV_USERS, 
                  "{} đã được ân xá từ gban!".format(mention_html(user_chat.id, 
                                                                         user_chat.first_name)),
                  html=True)

    message.reply_text("{} đã được bỏ cấm".format(mention_html(user_chat.id, user_chat.first_name)),
                        parse_mode=ParseMode.HTML)
    end_time = time.time()
    ungban_time = round((end_time - start_time), 2)

    if ungban_time > 60:
        ungban_time = round((ungban_time / 60), 2)
        message.reply_text(
            f"Done! This Ungban affected {ungbanned_chats} chats, Took {ungban_time} min")
    else:
        message.reply_text(f"Xong! Ungban này bị ảnh hưởng {ungbanned_chats} chats, Took {ungban_time} sec")
        
@run_async
def gbanlist(bot: Bot, update: Update):
    banned_users = sql.get_gban_list()

    if not banned_users:
        update.effective_message.reply_text("Không có bất kỳ người dùng nào bị cấm! Bạn tốt hơn tôi mong đợi ...")
        return

    banfile = 'Vặn những kẻ này. \n'
    for user in banned_users:
        banfile += "[x] {} - {}\n".format(user["name"], user["user_id"])
        if user["reason"]:
            banfile += "Reason: {}\n".format(user["reason"])

    with BytesIO(str.encode(banfile)) as output:
        output.name = "gbanlist.txt"
        update.effective_message.reply_document(document=output, filename="gbanlist.txt",
                                                caption="Đây là danh sách những người dùng bị cấm.")


def check_and_ban(update, user_id, should_message=True):
    chat = update.effective_chat
    message = update.effective_message
    if spam_watch != None:
        spam_watch_ban = spam_watch.get_ban(user_id)
        if spam_watch_ban:
            spamwatch_reason = spam_watch_ban.reason
            chat.kick_member(user_id)
            if should_message:
                message.reply_text(
                    (chat.id,
                        "<b>Người dùng này bị SpamWatch phát hiện là spambot và đã bị xóa!</b>\n\n<b>Reason</b>: {}").format(spamwatch_reason),
                    parse_mode=ParseMode.HTML)
                return
            else:
                return

    if sql.is_user_gbanned(user_id):
        chat.kick_member(user_id)
        if should_message:
            userr = sql.get_gbanned_user(user_id)
            usrreason = userr.reason
            if not usrreason:
                usrreason = (chat.id, "Không có lý do nào được đưa ra")

            message.reply_text((
                chat.id, "*Người dùng này đã bị cấm và đã bị xóa.*\nReason: `{}`").format(usrreason),
                               parse_mode=ParseMode.MARKDOWN)
            return

@run_async
def enforce_gban(bot: Bot, update: Update):
    # Not using @restrict handler to avoid spamming - just ignore if cant gban.
    if sql.does_chat_gban(update.effective_chat.id) and update.effective_chat.get_member(bot.id).can_restrict_members:
        user = update.effective_user  # type: Optional[User]
        chat = update.effective_chat  # type: Optional[Chat]
        msg = update.effective_message  # type: Optional[Message]

        if user and not is_user_admin(chat, user.id):
            check_and_ban(update, user.id)

        if msg.new_chat_members:
            new_members = update.effective_message.new_chat_members
            for mem in new_members:
                check_and_ban(update, mem.id)

        if msg.reply_to_message:
            user = msg.reply_to_message.from_user  # type: Optional[User]
            if user and not is_user_admin(chat, user.id):
                check_and_ban(update, user.id, should_message=False)


@run_async
@user_admin
def gbanstat(bot: Bot, update: Update, args: List[str]):
    if len(args) > 0:
        if args[0].lower() in ["on", "yes"]:
            sql.enable_gbans(update.effective_chat.id)
            update.effective_message.reply_text("Tôi đã kích hoạt gbans trong nhóm này. Điều này sẽ giúp bảo vệ bạn "
                                                "từ những kẻ gửi thư rác, những nhân vật không đáng tin cậy và những kẻ troll lớn nhất.")
        elif args[0].lower() in ["off", "no"]:
            sql.disable_gbans(update.effective_chat.id)
            update.effective_message.reply_text("Tôi đã tắt gbans trong nhóm này. GBans sẽ không ảnh hưởng đến người dùng của bạn "
                                                "nữa không. Bạn sẽ ít được bảo vệ khỏi bất kỳ kẻ troll và kẻ gửi thư rác nào "
                                                "though!")
    else:
        update.effective_message.reply_text("Hãy cho tôi một số đối số để chọn một thiết lập! on/off, yes/no!\n\n"
                                            "Cài đặt hiện tại của bạn là: {}\n"
                                            "Khi True, bất kỳ gbans nào xảy ra cũng sẽ xảy ra trong nhóm của bạn. "
                                            "Khi False, họ sẽ không, bỏ mặc bạn với sự thương xót có thể "
                                            "spammers.".format(sql.does_chat_gban(update.effective_chat.id)))

@run_async
def clear_gbans(bot: Bot, update: Update):
    '''Kiểm tra và xóa các tài khoản đã xóa khỏi gbanlist.
    By @ryostar'''
    banned = sql.get_gban_list()
    deleted = 0
    for user in banned:
        id = user["user_id"]
        time.sleep(0.1) # Reduce floodwait
        try:
            acc = bot.get_chat(id)
            if not acc.first_name:
                deleted += 1
                sql.ungban_user(id)
        except BadRequest:
            deleted += 1
            sql.ungban_user(id)
    update.message.reply_text("Done! `{}` tài khoản đã xóa đã bị xóa " \
    "từ danh sách gbanlist.".format(deleted), parse_mode=ParseMode.MARKDOWN)
    

@run_async
def check_gbans(bot: Bot, update: Update):
    '''By @ryostar'''
    banned = sql.get_gban_list()
    deleted = 0
    for user in banned:
        id = user["user_id"]
        time.sleep(0.1) # Reduce floodwait
        try:
            acc = bot.get_chat(id)
            if not acc.first_name:
                deleted += 1
        except BadRequest:
            deleted += 1
    if deleted:
        update.message.reply_text("`{}` tài khoản đã xóa được tìm thấy trong danh sách gbanlist! " \
        "Chạy /cleangb để xóa chúng khỏi cơ sở dữ liệu!".format(deleted),
        parse_mode=ParseMode.MARKDOWN)
    else:
        update.message.reply_text("Không có tài khoản bị xóa trong danh sách gbanlist!")

        
def __stats__():
    return "{} người dùng bị cấm.".format(sql.num_gbanned_users())


def __user_info__(user_id):
    is_gbanned = sql.is_user_gbanned(user_id)

    text = "Bị cấm trên toàn cầu: <b>{}</b>"
    if is_gbanned:
        text = text.format("Yes")
        user = sql.get_gbanned_user(user_id)
        if user.reason:
            text += "\nLý do: {}".format(html.escape(user.reason))
    else:
        text = text.format("No")
    return text


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    return "Trò chuyện này đang thực thi *gbans*: `{}`.".format(sql.does_chat_gban(chat_id))


__help__ = """
*Admin only:*
 - /gbanstat <on/off/yes/no>: Sẽ vô hiệu hóa ảnh hưởng của lệnh cấm toàn cầu đối với nhóm của bạn hoặc trả lại cài đặt hiện tại của bạn.

Gbans, còn được gọi là lệnh cấm toàn cầu, được chủ sở hữu bot sử dụng để cấm những người gửi thư rác trên tất cả các nhóm. Điều này giúp bảo vệ \
bạn và các nhóm của bạn bằng cách loại bỏ lũ spam càng nhanh càng tốt. Họ có thể bị vô hiệu hóa cho nhóm của bạn bằng cách gọi \
/gbanstat
- /checkgb : Để kiểm tra xem các Tài khoản đã Xóa có trong danh sách gban hay không.
- /cleangb : Để xóa tất cả các tài khoản đã xóa khỏi danh sách gban
"""

__mod_name__ = "SuperBan 😎"
GBAN_HANDLER = CommandHandler("gban", gban, pass_args=True,
                              filters=CustomFilters.sudo_filter | CustomFilters.support_filter)
UNGBAN_HANDLER = CommandHandler("ungban", ungban, pass_args=True,
                                filters=CustomFilters.sudo_filter | CustomFilters.support_filter)
GBAN_LIST = CommandHandler("gbanlist", gbanlist,
                           filters=CustomFilters.sudo_filter | CustomFilters.support_filter)

GBAN_STATUS = CommandHandler("gbanstat", gbanstat, pass_args=True, filters=Filters.group)
CHECK_GBAN_HANDLER = CommandHandler("checkgb", check_gbans, filters=Filters.user(OWNER_ID))
CLEAN_GBAN_HANDLER = CommandHandler("cleangb", clear_gbans, filters=Filters.user(OWNER_ID))

GBAN_ENFORCER = MessageHandler(Filters.all & Filters.group, enforce_gban)

dispatcher.add_handler(GBAN_HANDLER)
dispatcher.add_handler(UNGBAN_HANDLER)
dispatcher.add_handler(GBAN_LIST)
dispatcher.add_handler(GBAN_STATUS)
dispatcher.add_handler(CHECK_GBAN_HANDLER)
dispatcher.add_handler(CLEAN_GBAN_HANDLER)

if STRICT_GBAN:  # enforce GBANS if this is set
    dispatcher.add_handler(GBAN_ENFORCER, GBAN_ENFORCE_GROUP)
