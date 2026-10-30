#include <algorithm>
#include <cassert>
#include <iostream>
#include <string>

struct Label { std::string text; bool hidden = false; };
constexpr int LV_OBJ_FLAG_HIDDEN = 1;
void lv_label_set_text(Label* label, const char* text) { label->text = text; }
void lv_obj_add_flag(Label* label, int) { label->hidden = true; }
void lv_obj_remove_flag(Label* label, int) { label->hidden = false; }
class OledDisplay {
public:
    Label address, chat, content, right;
    Label* local_address_label_ = &address;
    Label* chat_message_label_ = &chat;
    Label* content_ = &content;
    Label* content_right_ = nullptr;
    int height_ = 32;
    bool chat_empty_ = true;
    std::string local_address_;
    void SetLocalAddress(const char* address);
    void UpdateLocalAddress();
    void SetChatMessage(const char* role, const char* content);
};
struct DisplayLockGuard { explicit DisplayLockGuard(OledDisplay*) {} };
#include "display_methods.inc"

int main() {
    for (int height : {32, 64}) {
        OledDisplay display;
        display.height_ = height;
        if (height == 64) display.content_right_ = &display.right;
        display.SetLocalAddress("");
        assert(display.address.text == "Wi-Fi offline" && !display.address.hidden);
        display.SetLocalAddress("192.168.100.200:8080");
        assert(display.address.text == "192.168.100.200:8080");
        // Startup and repeated idle transitions clear chat, not the address.
        display.SetChatMessage("system", "");
        display.SetChatMessage("system", "");
        assert(!display.address.hidden && display.chat.hidden);
        assert(display.content.hidden == (height == 32));
        display.SetChatMessage("assistant", "hello\nworld");
        assert(display.address.hidden && !display.chat.hidden);
        assert(display.chat.text == "hello world" && !display.content.hidden);
        display.SetLocalAddress("");
        assert(display.address.hidden && display.chat.text == "hello world");
        display.SetChatMessage("system", nullptr);
        assert(!display.address.hidden && display.address.text == "Wi-Fi offline");
        display.SetLocalAddress("10.0.0.2:8080");
        assert(!display.address.hidden && display.address.text == "10.0.0.2:8080");
        display.SetChatMessage("user", "question");
        display.SetLocalAddress("172.20.10.12:8080");
        assert(display.address.hidden && display.chat.text == "question");
        display.SetChatMessage("system", "");
        assert(!display.address.hidden && display.address.text == "172.20.10.12:8080");
    }
    std::cout << "PASS: OLED idle address, startup clear, speech, disconnect and IP change\n";
}
