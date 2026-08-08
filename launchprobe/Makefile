CC      = gcc
NVCC    = /usr/local/cuda/bin/nvcc
CFLAGS  = -O2 -Wall -Wextra -fPIC -Iinclude -g
LDFLAGS = -shared -ldl -lpthread

all: libnvtrace.so target/vecadd target/qmdprobe target/regprobe target/injectprobe target/construct target/cblaunch target/demo_kernel.cubin target/demo2_kernel.cubin

libnvtrace.so: src/nvtrace.c src/doorbell_trap.c src/mini_decode.c include/nvrm_ioctl.h
	$(CC) $(CFLAGS) -Isrc -o $@ src/nvtrace.c src/doorbell_trap.c src/mini_decode.c $(LDFLAGS)

target/vecadd: target/vecadd.cu
	$(NVCC) -arch=sm_120 -O2 -o $@ $<

target/qmdprobe: target/qmdprobe.cu
	$(NVCC) -arch=sm_120 -O2 -o $@ $<

target/regprobe: target/regprobe.c
	$(CC) -O2 -I/usr/local/cuda/include -o $@ $< -lcuda -ldl

target/injectprobe: target/injectprobe.cu
	$(NVCC) -arch=sm_120 -O2 -o $@ $<

target/construct: target/construct.cu
	$(NVCC) -arch=sm_120 -O2 -o $@ $<

target/cblaunch: target/cblaunch.cu target/demo_kernel.cu target/demo2_kernel.cu
	$(NVCC) -arch=sm_120 -O2 -o $@ target/cblaunch.cu

target/demo_kernel.cubin: target/demo_kernel.cu
	$(NVCC) -arch=sm_120 -O2 -cubin -o $@ $<

target/demo2_kernel.cubin: target/demo2_kernel.cu
	$(NVCC) -arch=sm_120 -O2 -cubin -o $@ $<

clean:
	rm -f libnvtrace.so target/vecadd target/qmdprobe target/regprobe target/injectprobe target/construct target/cblaunch target/demo_kernel.cubin target/demo2_kernel.cubin

.PHONY: all clean
