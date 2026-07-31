from __future__ import annotations

STRINGS = {
    "start_greeting": (
        "Xin chào! Tôi là bot trợ lý tạo nội dung cho mạng xã hội và cho "
        "trang web cá nhân của bạn — tôi viết theo phong cách riêng độc "
        "đáo của bạn, bằng tiếng Nga, tiếng Anh, tiếng Trung và tiếng "
        "Việt.\n\n"
        "Hãy gửi cho tôi đường liên kết đến bài viết, tin nhắn thoại, "
        "văn bản, hoặc mô tả hình ảnh bạn muốn — tôi sẽ chuẩn bị các "
        "phương án bài đăng sẵn sàng sử dụng cho Telegram và VK.\n\n"
        "Để đổi ngôn ngữ giao diện, hãy dùng lệnh /language."
    ),
    "language_prompt": "Chọn ngôn ngữ giao diện:",
    "language_set_confirmation": "Đã đổi ngôn ngữ giao diện sang tiếng Việt.",
    "error_ai_timeout": (
        "Dịch vụ tạo nội dung hiện đang phản hồi chậm hơn bình thường. "
        "Vui lòng thử lại sau vài phút."
    ),
    "error_rate_limit": (
        "Hiện có quá nhiều yêu cầu gửi đến dịch vụ tạo nội dung cùng lúc. "
        "Vui lòng đợi một chút rồi thử lại."
    ),
    "error_ai_unavailable": (
        "Không thể kết nối với dịch vụ tạo nội dung. Chúng tôi đã biết về "
        "sự cố này — vui lòng thử lại sau."
    ),
    "error_invalid_ai_response": (
        "Không nhận được phản hồi hợp lệ từ mô hình AI. Vui lòng thử lại "
        "yêu cầu."
    ),
    "error_transcription": (
        "Không thể nhận dạng tin nhắn thoại. Vui lòng gửi lại hoặc nhập "
        "văn bản thay thế — cách đó cũng có tác dụng."
    ),
    "error_out_of_budget": (
        "Dịch vụ tạo nội dung tạm thời không khả dụng vì lý do kỹ thuật. "
        "Chủ sở hữu đã được thông báo — việc này thường được xử lý trong "
        "vài giờ. Vui lòng thử lại sau."
    ),
    "error_voice_too_long": (
        "Tin nhắn thoại dài hơn {limit_minutes} phút — tôi không nhận dạng "
        "được. Vui lòng ghi ngắn hơn hoặc gửi văn bản."
    ),
    "error_daily_image_limit": (
        "Hôm nay đã hết ảnh — giới hạn là {limit} ảnh mỗi ngày. Văn bản bài "
        "viết vẫn hoạt động, ảnh sẽ mở lại vào ngày mai."
    ),
    "error_link_extraction": (
        "Không thể trích xuất văn bản từ đường liên kết này — có thể "
        "trang web được bảo vệ khỏi việc đọc tự động hoặc tạm thời không "
        "khả dụng. Hãy thử liên kết khác hoặc gửi trực tiếp văn bản của "
        "bài viết."
    ),
    "error_unexpected": (
        "Đã có lỗi xảy ra ở phía chúng tôi. Chúng tôi đã nhận được thông "
        "báo về việc này — vui lòng thử lại yêu cầu sau."
    ),
    "error_not_whitelisted": (
        "Quyền truy cập bot này hiện đang giới hạn cho danh sách người "
        "dùng được mời. Nếu bạn cho rằng mình nên có quyền truy cập, hãy "
        "liên hệ với chủ sở hữu bot."
    ),
    "error_daily_limit_exceeded": (
        "Bạn đã dùng hết hạn mức yêu cầu trong ngày hôm nay. Hạn mức mới "
        "sẽ có vào ngày mai."
    ),
    "error_monthly_limit_exceeded": (
        "Bạn đã dùng hết hạn mức yêu cầu trong tháng này. Hạn mức mới sẽ "
        "có vào tháng sau."
    ),
    "onboarding_capabilities": (
        "Tôi có thể làm gì:\n\n"
        "— Nhận đường liên kết bài viết, tin nhắn thoại, hoặc văn bản "
        "thường — và chuẩn bị nhiều phương án bài đăng, riêng cho "
        "Telegram và riêng cho VK, viết theo phong cách riêng của "
        "bạn.\n"
        "— Viết bằng tiếng Nga, tiếng Anh, tiếng Trung và tiếng Việt.\n"
        "— Có thể tạo hình ảnh theo mô tả của bạn — riêng lẻ hoặc bổ "
        "sung cho bài đăng.\n"
        "— Đăng bài trực tiếp vào kênh Telegram của bạn chỉ bằng một "
        "nút bấm (lệnh /channel).\n"
        "— Lấy và cập nhật thẻ dịch vụ trên trang web cá nhân của bạn "
        "ngay trong chat (lệnh /site).\n\n"
        "Các lệnh: /start — bắt đầu lại, /language — đổi ngôn ngữ giao "
        "diện, /channel — thiết lập kênh, /site — làm việc với trang "
        "web, /clear_media — bỏ tệp đính kèm, /settov — dạy bot phong "
        "cách viết của bạn, /help — hiển thị lại tin nhắn này."
    ),
    "onboarding_settov": (
        "Muốn bài đăng nghe giống văn phong của bạn? Hãy gửi lệnh /settov "
        "và gửi vài bài đăng cũ của bạn — bot sẽ ghi nhớ chúng và dùng làm "
        "tham chiếu khi tạo bài đăng mới."
    ),
    "onboarding_quick_start": (
        "Bắt đầu nhanh: hãy gửi cho tôi một đường liên kết bài viết hoặc "
        "một tin nhắn thoại — chỉ sau vài giây bạn sẽ nhận được các "
        "phương án bài đăng sẵn sàng sử dụng."
    ),
    "start_button_label": "Bắt đầu",
    "command_start_description": "Khởi động bot",
    "menu_intro": "Tiếp theo chúng ta làm gì?",
    "menu_capabilities_button": "Tôi có thể làm gì",
    "menu_cta_button": "Tạo bài đăng ngay",
    "menu_news_digest_button": "Tổng hợp tin tức mới nhất",
    "menu_digest_write_topic_button": "Viết chủ đề bạn quan tâm",
    "menu_digest_change_topic_button": "Đổi chủ đề",
    "digest_prompt_no_topic": (
        "Để tổng hợp bản tin, trước tiên hãy cho tôi biết chủ đề bạn quan tâm."
    ),
    "digest_change_topic_prompt": "Bạn có muốn tổng hợp bản tin theo chủ đề khác không?",
    "digest_topic_input_prompt": "Viết chủ đề cần tổng hợp bản tin:",
    "digest_topic_input_placeholder": "Ví dụ: tâm lý học",
    "digest_topic_saved": "Đã lưu chủ đề: «{topic}». Đang tổng hợp bản tin...",
    "digest_title": "📋 Bản tin theo chủ đề «{topic}» ngày {date}",
    "digest_section_news": "📰 Trong tin tức",
    "digest_section_papers": "🔬 Bài báo khoa học",
    "digest_section_methods": "💡 Phương pháp mới",
    "digest_empty_result": (
        "Không tìm thấy gì về «{topic}» hôm nay. Hãy thử chủ đề khác hoặc "
        "quay lại sau."
    ),
    "menu_text_generation_button": "Tạo văn bản",
    "menu_text_generation_hint": (
        "Hãy gửi cho tôi đường liên kết bài viết, tin nhắn thoại, hoặc "
        "văn bản — tôi sẽ chuẩn bị các phương án bài đăng cho Telegram "
        "và VK."
    ),
    "menu_photo_generation_button": "Tạo ảnh",
    "photo_gen_prompt": "Hãy mô tả hình ảnh bạn muốn — tôi sẽ tạo nó bằng AI.",
    "photo_gen_ready": (
        "Hình ảnh đã sẵn sàng! Bây giờ hãy gửi văn bản, đường liên kết "
        "bài viết, hoặc tin nhắn thoại — tôi sẽ chuẩn bị bài đăng kèm "
        "hình ảnh này."
    ),
    "transcript_preview": (
        "Đây là nội dung tôi nghe được trong tin nhắn thoại của bạn:\n\n"
        "{text}\n\nCó đúng không?"
    ),
    "transcript_confirm_button": "Đúng rồi",
    "transcript_edit_button": "Sửa lại",
    "transcript_edit_prompt": "Vui lòng gửi văn bản đã chỉnh sửa.",
    "content_ready_stub": (
        "Đã nhận văn bản! Tạo bài đăng vẫn đang được phát triển — sắp "
        "tới tôi sẽ biến nó thành các phiên bản sẵn sàng sử dụng cho "
        "Telegram và VK."
    ),
    "refine_more_button": "Thêm phương án",
    "refine_shorten_button": "Ngắn hơn",
    "error_refine_missing_context": (
        "Tôi không tìm thấy văn bản gốc để chỉnh sửa — vui lòng gửi lại "
        "tài liệu."
    ),
    "channel_setup_instructions": (
        "Để đăng bài chỉ bằng một nút bấm, hãy thiết lập kênh của bạn:\n\n"
        "1. Thêm bot này làm quản trị viên của kênh Telegram của bạn với "
        "quyền đăng bài.\n"
        "2. Chuyển tiếp bất kỳ tin nhắn nào từ kênh đó đến đây — tôi sẽ "
        "dùng nó để xác định kênh."
    ),
    "channel_setup_invalid_forward": (
        "Đây không phải là tin nhắn được chuyển tiếp từ kênh. Vui lòng "
        "chuyển tiếp một tin nhắn bất kỳ từ kênh Telegram của bạn."
    ),
    "channel_setup_bot_not_admin": (
        "Tôi không có quyền quản trị viên với quyền đăng bài trong kênh "
        "này. Hãy đảm bảo bot đã được thêm làm quản trị viên kênh và bật "
        "quyền \"Đăng tin nhắn\", sau đó chuyển tiếp lại một tin nhắn từ "
        "kênh."
    ),
    "channel_setup_confirmation": (
        "Xong! Kênh đã được thiết lập — giờ bạn có thể đăng bài vào kênh "
        "chỉ bằng một nút bấm."
    ),
    "publish_to_channel_button": "Đăng vào kênh",
    "publish_no_channel_configured": (
        "Chưa thiết lập kênh nào. Hãy dùng lệnh /channel để kết nối kênh "
        "Telegram của bạn."
    ),
    "publish_success": "Bài đăng đã được đăng vào kênh của bạn.",
    "publish_failed": (
        "Không thể đăng bài vào kênh — có thể bot đã mất quyền quản trị "
        "viên. Hãy kiểm tra quyền và thiết lập lại kênh qua /channel."
    ),
    "media_attached_confirmation": (
        "Đã nhận ảnh/video! Nó sẽ được đính kèm vào bài đăng tiếp theo mà "
        "bạn đăng lên kênh. Để bỏ tệp đính kèm, hãy dùng lệnh /clear_media."
    ),
    "media_cleared_confirmation": "Đã bỏ tệp đính kèm — bài đăng tiếp theo sẽ không có nó.",
    "media_nothing_to_clear": "Hiện không có ảnh hoặc video nào được đính kèm.",
    "generate_image_button": "🖼 Ảnh từ AI",
    "image_preview_caption": "Xem trước ảnh do AI tạo",
    "image_delivery_failed": "Không thể gửi ảnh — vui lòng thử lại sau.",
    "image_attached_confirmation": (
        "Ảnh do AI tạo đã sẵn sàng và được đính kèm — nó sẽ được dùng cho "
        "bài đăng tiếp theo bạn đăng lên kênh. Để bỏ tệp đính kèm, hãy dùng "
        "lệnh /clear_media."
    ),
    "image_upgrade_button": "🎨 Làm ảnh chân thực hơn (~15₽)",
    "image_upgraded_button": "✅ Xong",
    "image_upgraded_caption": "✨ Phiên bản chân thực hơn",
    "settov_instructions": (
        "Hãy gửi cho tôi một vài bài đăng cũ của bạn — mỗi bài một tin "
        "nhắn riêng, dạng văn bản thường. Tôi sẽ dùng chúng làm tham chiếu "
        "phong cách khi tạo bài đăng mới.\n\n"
        "Khi đã gửi xong tất cả các ví dụ, hãy nhấn nút «Xong»."
    ),
    "settov_done_button": "Xong",
    "settov_example_saved": "Đã lưu ví dụ! Gửi thêm một ví dụ nữa hoặc nhấn «Xong».",
    "settov_example_too_long": (
        "Ví dụ này quá dài. Vui lòng gửi một ví dụ ngắn hơn (tối đa 2000 "
        "ký tự)."
    ),
    "settov_non_text_reprompt": (
        "Vui lòng gửi ví dụ dưới dạng tin nhắn văn bản thường, hoặc nhấn "
        "«Xong» nếu bạn đã có đủ ví dụ."
    ),
    "settov_finished_confirmation": (
        "Xong! Đã lưu số ví dụ phong cách: {count}. Tôi sẽ dựa vào chúng "
        "khi tạo các bài đăng mới."
    ),
    "site_menu_intro": (
        "Ở đây bạn có thể mở trang web hoặc lấy nội dung thẻ dịch vụ về để chỉnh sửa."
    ),
    "open_site_button": "TRANG WEB CỦA TÔI",
    "pull_from_site_button": "Lấy thẻ 'Dịch vụ'",
    "site_push_button": "Đăng lên trang web",
    "site_pull_empty": (
        "Chưa có nội dung nào được đăng cho thẻ này trên trang web — hãy "
        "dùng nút 'Đăng lên trang web' trước."
    ),
    "site_push_success": "Xong! Thẻ trên trang web đã được cập nhật.",
    "site_push_photo_failed": "Không thể tải ảnh cho trang web — vui lòng thử lại sau.",
    "authorpost_button": "✍️ VIẾT BÀI ĐĂNG CỦA RIÊNG TÔI",
    "authorpost_digest_expired": (
        "Bản tin này đã cũ — hãy tổng hợp bản tin mới, nút viết bài sẽ "
        "hoạt động trở lại."
    ),
    "authorpost_choose_item": "Viết bài về mục nào trong bản tin?",
    "authorpost_item_chosen": "Tuyệt, chọn mục: {item}",
    "authorpost_next_button": "Tôi sẽ giúp bạn viết — nhấn để tiếp tục",
    "authorpost_saved_examples_intro": (
        "Tôi đã biết văn phong của bạn — số ví dụ đã lưu: {count}. Viết "
        "theo chúng hay tải lên ví dụ mới?"
    ),
    "authorpost_use_saved_button": "Viết ngay",
    "authorpost_new_samples_button": "Tải lên ví dụ mới",
    "authorpost_samples_cleared": "Đã xóa ví dụ cũ. Hãy gửi ví dụ mới.",
    "authorpost_samples_prompt": (
        "Hãy dán các bài đăng của bạn — ít nhất {required} bài. Gửi lần "
        "lượt, mỗi bài một tin nhắn, dạng văn bản thường. Tôi sẽ đọc ra "
        "văn phong riêng của bạn."
    ),
    "authorpost_samples_progress": "Đã nhận {count} trên {required}.",
    "authorpost_samples_enough": (
        "Đã nhận {count} trên {required} ✅ Vậy là đủ. Gửi thêm cho chính "
        "xác hơn, hoặc nhấn nút."
    ),
    "authorpost_samples_done_button": "✒ Viết bài theo chủ đề đã chọn",
    "style_read_summary": (
        "Đã nắm được văn phong của bạn ✅\n\n"
        "Bạn viết như thế nào:\n"
        "{summary}\n\n"
        "Tôi sẽ viết đúng như vậy."
    ),
    "style_button_own_topic": "✍ Bài viết theo chủ đề của tôi",
    "style_button_fresh_digest": "📰 Bài viết từ bản tin mới",
    "style_own_topic_prompt": (
        "Hãy gửi một chủ đề hoặc một đoạn văn bản — tôi sẽ viết thành bài "
        "theo văn phong của bạn. Bạn cũng có thể gửi liên kết hoặc tin nhắn thoại."
    ),
    "authorpost_sample_too_long": (
        "Ví dụ này quá dài. Vui lòng gửi một ví dụ ngắn hơn (tối đa 2000 "
        "ký tự)."
    ),
    "authorpost_sample_non_text": (
        "Vui lòng gửi ví dụ dưới dạng tin nhắn văn bản thường."
    ),
    "authorpost_choose_platform": "Đăng ở đâu?",
    "authorpost_platform_telegram_button": "Telegram",
    "authorpost_platform_vk_button": "VK",
    "authorpost_platform_both_button": "Cả hai",
    "authorpost_generating": "Đang viết bài theo văn phong của bạn...",
    "package_button": "📦 Gói cho mạng xã hội",
    "package_intro": (
        "Các gói sẵn sàng cho Instagram, YouTube Shorts và Facebook.\n\n"
        "Phần văn bản trong khung có thể sao chép bằng một chạm — hãy dán vào "
        "ứng dụng của nền tảng và tự đăng. Bot không đăng thay bạn và không "
        "yêu cầu quyền truy cập tài khoản của bạn."
    ),
    "package_title_label": "Tiêu đề:",
    "package_body_label": "Mô tả:",
    "package_media_spec": "📐 Video: {aspect}, {resolution}, {seconds}",
    "package_note_links_not_clickable": (
        "🔗 Liên kết trong chú thích ở đây không bấm được — hãy đưa liên kết "
        "vào phần tiểu sử hồ sơ (tìm thấy trong văn bản: {count})"
    ),
    "package_note_caption_truncated": (
        "✂️ Văn bản đã bị cắt theo giới hạn của nền tảng — {limit} ký tự"
    ),
    "package_note_hashtags_trimmed": (
        "#️⃣ Hashtag đã rút còn {max} — mức phù hợp với nền tảng này"
    ),
    "package_note_preview": (
        "👀 Chỉ {preview} ký tự đầu hiển thị trước «xem thêm» — hãy đặt câu móc "
        "vào trong đó"
    ),
    "package_note_ai_disclosure": (
        "🤖 Khi tải lên, hãy đánh dấu video được tạo bằng AI (trên YouTube đây "
        "là yêu cầu bắt buộc)"
    ),
}
