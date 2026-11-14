#version 450

layout(location = 0) out vec4 out_color;

void main()
{
    out_color = vec4(gl_HelperInvocation ? 1.0 : 0.0);
}
