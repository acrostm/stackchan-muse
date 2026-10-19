#pragma once

/* Host tests are single-threaded; production uses ESP-IDF's short,
 * non-preemptive critical section instead of a priority-inverting spin lock. */
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define taskENTER_CRITICAL(mux) ((void)(mux))
#define taskEXIT_CRITICAL(mux) ((void)(mux))
