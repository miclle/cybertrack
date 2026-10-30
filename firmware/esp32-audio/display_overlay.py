"""Keep the LAN address readable on the pinned OLED while chat is idle."""


METHODS = '''void OledDisplay::SetLocalAddress(const char* address) {
    DisplayLockGuard lock(this);
    local_address_ = address ? address : "";
    UpdateLocalAddress();
}

void OledDisplay::UpdateLocalAddress() {
    // Called only with the display lock held. Chat and network events share it.
    if (local_address_label_ == nullptr) return;
    lv_label_set_text(local_address_label_, local_address_.empty()
        ? "Wi-Fi offline" : local_address_.c_str());
    if (chat_empty_) {
        lv_obj_remove_flag(local_address_label_, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(chat_message_label_, LV_OBJ_FLAG_HIDDEN);
        // The 32-pixel emoji overlaps the full-width address on the 32px panel.
        if (height_ == 32) lv_obj_add_flag(content_, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(local_address_label_, LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(chat_message_label_, LV_OBJ_FLAG_HIDDEN);
        if (height_ == 32) lv_obj_remove_flag(content_, LV_OBJ_FLAG_HIDDEN);
    }
}

'''

SETUP = '''
    // A separate full-width line survives status changes and cleared chat text.
    {
        DisplayLockGuard lock(this);
        local_address_label_ = lv_label_create(lv_screen_active());
        lv_obj_set_size(local_address_label_, width_, 16);
        lv_obj_align(local_address_label_, LV_ALIGN_BOTTOM_MID, 0, 0);
        lv_obj_set_style_text_font(local_address_label_, &lv_font_montserrat_10, 0);
        lv_obj_set_style_text_color(local_address_label_, lv_color_black(), 0);
        lv_obj_set_style_bg_color(local_address_label_, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(local_address_label_, LV_OPA_COVER, 0);
        lv_obj_set_style_text_align(local_address_label_, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_set_style_pad_top(local_address_label_, 2, 0);
        lv_label_set_long_mode(local_address_label_, LV_LABEL_LONG_CLIP);
        UpdateLocalAddress();
    }
'''


def apply(source, replace):
    """Patch only the disposable export; reject changed upstream anchors."""
    base = source / "main/display/display.h"
    header = source / "main/display/oled_display.h"
    code = source / "main/display/oled_display.cc"
    replace(base, "    virtual void SetStatus(const char* status);",
            "    virtual void SetLocalAddress(const char* address) {}\n"
            "    virtual void SetStatus(const char* status);")
    replace(header, "    lv_obj_t* side_bar_ = nullptr;",
            "    lv_obj_t* local_address_label_ = nullptr;\n"
            "    std::string local_address_;\n"
            "    bool chat_empty_ = true;\n"
            "    void UpdateLocalAddress();\n\n    lv_obj_t* side_bar_ = nullptr;")
    replace(header, "    virtual void SetChatMessage",
            "    void SetLocalAddress(const char* address) override;\n"
            "    virtual void SetChatMessage")
    replace(code, "        SetupUI_128x32();\n    }\n}",
            "        SetupUI_128x32();\n    }\n" + SETUP + "}")
    replace(code, "OledDisplay::~OledDisplay() {",
            "OledDisplay::~OledDisplay() {\n"
            "    if (local_address_label_ != nullptr) lv_obj_del(local_address_label_);")
    replace(code, "void OledDisplay::SetChatMessage(", METHODS + "void OledDisplay::SetChatMessage(")
    replace(code, "    std::string content_str = content;",
            "    chat_empty_ = content == nullptr || content[0] == '\\0';\n"
            "    UpdateLocalAddress();\n"
            "    std::string content_str = content ? content : \"\";")
    replace(source / "sdkconfig", "# CONFIG_LV_FONT_MONTSERRAT_10 is not set",
            "CONFIG_LV_FONT_MONTSERRAT_10=y")
    replace(source / "main/application.cc",
            "        case kDeviceStateIdle:\n"
            "            display->SetStatus(Lang::Strings::STANDBY);",
            "        case kDeviceStateIdle:\n"
            "            display->SetChatMessage(\"system\", \"\");\n"
            "            display->SetStatus(Lang::Strings::STANDBY);")
