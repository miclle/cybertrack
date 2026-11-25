#include "stm32f0xx.h"
#include <stdbool.h>
#include <stdint.h>

enum { ADDRESS = 0x32, FRAME_BYTES = 17 };
static volatile uint32_t counts[2], milliseconds;
static uint16_t previous[2];
static bool reset_pending = true;

static void alternate(GPIO_TypeDef *port, unsigned pin, unsigned function) {
    unsigned shift = 4 * (pin % 8);
    port->AFR[pin / 8] = (port->AFR[pin / 8] & ~(15u << shift)) | (function << shift);
    port->MODER = (port->MODER & ~(3u << (pin * 2))) | (2u << (pin * 2));
}

static void quadrature(TIM_TypeDef *timer) {
    timer->ARR = UINT16_MAX;
    // TI1 and TI2 are direct inputs. ICxF=3 requires eight samples at fCK_INT.
    timer->CCMR1 = TIM_CCMR1_CC1S_0 | TIM_CCMR1_CC2S_0 |
                   (3u << TIM_CCMR1_IC1F_Pos) | (3u << TIM_CCMR1_IC2F_Pos);
    timer->SMCR = TIM_SMCR_SMS_0 | TIM_SMCR_SMS_1;
    timer->CCER = TIM_CCER_CC1E | TIM_CCER_CC2E;
    timer->EGR = TIM_EGR_UG;
    timer->CR1 = TIM_CR1_CEN;
}

static uint32_t accumulate(uint16_t raw, unsigned side) {
    uint16_t delta = (uint16_t)(raw - previous[side]);
    previous[side] = raw;
    return delta < 0x8000u ? delta : (uint32_t)delta - 65536u;
}

void SysTick_Handler(void) {
    counts[0] += accumulate((uint16_t)TIM1->CNT, 0);
    counts[1] += accumulate((uint16_t)TIM3->CNT, 1);
    ++milliseconds;
}

static void put32(uint8_t *bytes, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) bytes[i] = (uint8_t)(value >> (8 * i));
}

static void snapshot(uint8_t frame[FRAME_BYTES]) {
    __disable_irq();
    uint32_t tick = milliseconds, a = counts[0], b = counts[1];
    __enable_irq();
    frame[0] = 'C';
    frame[1] = 'T';
    frame[2] = 1;
    frame[3] = reset_pending;
    put32(frame + 4, tick);
    put32(frame + 8, a);
    put32(frame + 12, b);
    uint8_t crc = 0;
    for (unsigned i = 0; i < FRAME_BYTES - 1; ++i) {
        crc ^= frame[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x07 : 0));
    }
    frame[16] = crc;
}

static void serve(void) {
    uint8_t frame[FRAME_BYTES] = {0};
    uint8_t sent = 0, received = 0;
    bool ack_reset = false;
    for (;;) {
        uint32_t flags = I2C1->ISR;
        if (flags & (I2C_ISR_BERR | I2C_ISR_ARLO | I2C_ISR_OVR)) {
            ack_reset = false;
            I2C1->ICR = I2C_ICR_BERRCF | I2C_ICR_ARLOCF | I2C_ICR_OVRCF;
        }
        // Drain the last RX byte before processing a simultaneous STOP or repeated START.
        if (flags & I2C_ISR_RXNE) {
            uint8_t byte = (uint8_t)I2C1->RXDR;
            ack_reset &= (received == 0 && byte == 0xa5) || (received == 1 && byte == 0x5a);
            if (received < 3) ++received;
        }
        if (flags & I2C_ISR_NACKF) I2C1->ICR = I2C_ICR_NACKCF;
        if (flags & I2C_ISR_STOPF) {
            if (ack_reset && received == 2) reset_pending = false;
            ack_reset = false;
            I2C1->ICR = I2C_ICR_STOPCF;
        }
        if (flags & I2C_ISR_ADDR) {
            bool read = (flags & I2C_ISR_DIR) != 0;
            received = sent = 0;
            ack_reset = !read;
            I2C1->ISR = I2C_ISR_TXE; // Discard any unsent byte from a short read.
            if (read) snapshot(frame);
            I2C1->ICR = I2C_ICR_ADDRCF;
        }
        if (I2C1->ISR & I2C_ISR_TXIS)
            I2C1->TXDR = sent < FRAME_BYTES ? frame[sent++] : 0xff;
    }
}

int main(void) {
    RCC->AHBENR |= RCC_AHBENR_GPIOAEN | RCC_AHBENR_GPIOBEN;
    RCC->APB2ENR |= RCC_APB2ENR_TIM1EN;
    RCC->APB1ENR |= RCC_APB1ENR_TIM3EN | RCC_APB1ENR_I2C1EN;
    alternate(GPIOA, 8, 2);
    alternate(GPIOA, 9, 2);
    alternate(GPIOA, 6, 1);
    alternate(GPIOA, 7, 1);
    quadrature(TIM1);
    quadrature(TIM3);
    SystemCoreClockUpdate();
    SysTick_Config(SystemCoreClock / 1000);

    GPIOB->OTYPER |= (1u << 6) | (1u << 7);
    alternate(GPIOB, 6, 1);
    alternate(GPIOB, 7, 1);
    // HSI 8 MHz I2C kernel, analog filter enabled, slave clock stretching enabled.
    RCC->CFGR3 &= ~RCC_CFGR3_I2C1SW;
    I2C1->TIMINGR = 0x0010020au;
    I2C1->OAR1 = I2C_OAR1_OA1EN | (ADDRESS << 1);
    I2C1->CR1 = I2C_CR1_PE;
    serve();
}
