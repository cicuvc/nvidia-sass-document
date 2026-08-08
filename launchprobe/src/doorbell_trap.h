#pragma once
#include <stdbool.h>
#include <stddef.h>

void doorbell_trap_install(void);
void doorbell_trap_set_enabled(bool en);
void doorbell_trap_register(void *addr, size_t len, int prot, int fd, int dev);
