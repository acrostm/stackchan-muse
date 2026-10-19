#pragma once
#define SHUT_RDWR 2
int muse_fake_shutdown(int, int);
#define shutdown muse_fake_shutdown
