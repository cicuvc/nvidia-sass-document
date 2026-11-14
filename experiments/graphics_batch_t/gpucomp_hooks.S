	.text
	.macro HOOK num
	.globl gpucomp_hook_\num
	.type gpucomp_hook_\num,@function
gpucomp_hook_\num:
	subq $0xe8, %rsp
	movq %rdi, 0x00(%rsp)
	movq %rsi, 0x08(%rsp)
	movq %rdx, 0x10(%rsp)
	movq %rcx, 0x18(%rsp)
	movq %r8,  0x20(%rsp)
	movq %r9,  0x28(%rsp)
	movq %rax, 0xc8(%rsp)
	movdqu %xmm0, 0x30(%rsp)
	movdqu %xmm1, 0x40(%rsp)
	movdqu %xmm2, 0x50(%rsp)
	movdqu %xmm3, 0x60(%rsp)
	movdqu %xmm4, 0x70(%rsp)
	movdqu %xmm5, 0x80(%rsp)
	movdqu %xmm6, 0x90(%rsp)
	movdqu %xmm7, 0xa0(%rsp)
	movl $\num, %edi
	leaq 0x00(%rsp), %rsi
	leaq 0x30(%rsp), %rdx
	call gpucomp_hook_log
	movq 0x00(%rsp), %rdi
	movq 0x08(%rsp), %rsi
	movq 0x10(%rsp), %rdx
	movq 0x18(%rsp), %rcx
	movq 0x20(%rsp), %r8
	movq 0x28(%rsp), %r9
	movq 0xc8(%rsp), %rax
	movdqu 0x30(%rsp), %xmm0
	movdqu 0x40(%rsp), %xmm1
	movdqu 0x50(%rsp), %xmm2
	movdqu 0x60(%rsp), %xmm3
	movdqu 0x70(%rsp), %xmm4
	movdqu 0x80(%rsp), %xmm5
	movdqu 0x90(%rsp), %xmm6
	movdqu 0xa0(%rsp), %xmm7
	addq $0xe8, %rsp
	movq gpucomp_real_table@GOTPCREL(%rip), %r11
	movq (\num*8)(%r11), %r11
	jmp *%r11
	.size gpucomp_hook_\num, .-gpucomp_hook_\num
	.endm

	.macro HOOK_CALL num
	.globl gpucomp_hook_\num
	.type gpucomp_hook_\num,@function
gpucomp_hook_\num:
	subq $0xe8, %rsp
	movq %rdi, 0x00(%rsp)
	movq %rsi, 0x08(%rsp)
	movq %rdx, 0x10(%rsp)
	movq %rcx, 0x18(%rsp)
	movq %r8,  0x20(%rsp)
	movq %r9,  0x28(%rsp)
	movq %rax, 0xc8(%rsp)
	movdqu %xmm0, 0x30(%rsp)
	movdqu %xmm1, 0x40(%rsp)
	movdqu %xmm2, 0x50(%rsp)
	movdqu %xmm3, 0x60(%rsp)
	movdqu %xmm4, 0x70(%rsp)
	movdqu %xmm5, 0x80(%rsp)
	movdqu %xmm6, 0x90(%rsp)
	movdqu %xmm7, 0xa0(%rsp)
	movl $\num, %edi
	leaq 0x00(%rsp), %rsi
	leaq 0x30(%rsp), %rdx
	call gpucomp_hook_log
	movq 0x00(%rsp), %rdi
	movq 0x08(%rsp), %rsi
	movq 0x10(%rsp), %rdx
	movq 0x18(%rsp), %rcx
	movq 0x20(%rsp), %r8
	movq 0x28(%rsp), %r9
	movq 0xc8(%rsp), %rax
	movdqu 0x30(%rsp), %xmm0
	movdqu 0x40(%rsp), %xmm1
	movdqu 0x50(%rsp), %xmm2
	movdqu 0x60(%rsp), %xmm3
	movdqu 0x70(%rsp), %xmm4
	movdqu 0x80(%rsp), %xmm5
	movdqu 0x90(%rsp), %xmm6
	movdqu 0xa0(%rsp), %xmm7
	movq gpucomp_real_table@GOTPCREL(%rip), %r11
	movq (\num*8)(%r11), %r11
	call *%r11
	movq %rax, 0xb0(%rsp)
	movq %rdx, 0xb8(%rsp)
	movdqu %xmm0, 0xd0(%rsp)
	movl $\num, %edi
	leaq 0x00(%rsp), %rsi
	leaq 0x30(%rsp), %rdx
	leaq 0xb0(%rsp), %rcx
	call gpucomp_hook_return
	movq 0xb0(%rsp), %rax
	movq 0xb8(%rsp), %rdx
	movdqu 0xd0(%rsp), %xmm0
	addq $0xe8, %rsp
	ret
	.size gpucomp_hook_\num, .-gpucomp_hook_\num
	.endm

	HOOK 0
	HOOK 1
	HOOK 2
	HOOK 3
	HOOK 4
	HOOK 5
	HOOK_CALL 6
	HOOK 7
	HOOK_CALL 8
	HOOK 9
	HOOK 10
	HOOK 11
	HOOK 12

	.section .note.GNU-stack,"",@progbits
