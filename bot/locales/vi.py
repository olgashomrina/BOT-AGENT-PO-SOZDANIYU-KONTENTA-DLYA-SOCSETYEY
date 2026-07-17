from __future__ import annotations

STRINGS = {
    "start_greeting": (
        "Xin chào! Tôi là bot trợ lý tạo nội dung cho mạng xã hội.\n\n"
        "Sắp tới tôi sẽ học cách biến đường liên kết, tin nhắn thoại và "
        "văn bản thành các bài đăng sẵn sàng sử dụng cho Telegram và VK. "
        "Tôi vẫn đang được phát triển — hiện tại lệnh này chỉ hoạt động "
        "như một bản nháp.\n\n"
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
    "error_limit_exceeded": (
        "Bạn đã dùng hết hạn mức yêu cầu trong ngày hôm nay. Hạn mức mới "
        "sẽ có vào ngày mai."
    ),
    "help_text": (
        "Hãy gửi cho tôi một đường liên kết bài viết, một tin nhắn thoại, "
        "hoặc chỉ cần văn bản — tôi sẽ giúp biến nó thành bài đăng sẵn "
        "sàng cho Telegram và VK.\n\n"
        "Các lệnh:\n"
        "/start — bắt đầu lại\n"
        "/language — đổi ngôn ngữ giao diện\n"
        "/help — hiển thị tin nhắn này"
    ),
    "content_stub_link": (
        "Tôi thấy một đường liên kết! Xử lý liên kết vẫn đang được phát "
        "triển — sắp tới tôi sẽ biến nó thành bài đăng hoàn chỉnh."
    ),
    "content_stub_voice": (
        "Đã nhận tin nhắn thoại! Nhận dạng giọng nói vẫn đang được phát "
        "triển — sắp tới tôi sẽ biến nó thành bài đăng hoàn chỉnh."
    ),
    "content_stub_text": (
        "Đã nhận văn bản! Tạo bài đăng vẫn đang được phát triển — sắp "
        "tới tôi sẽ biến nó thành các phiên bản sẵn sàng sử dụng."
    ),
}
