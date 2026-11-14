#version 450

layout(location = 0) out uvec4 out_color;

void main()
{
    out_color = uvec4(0x11111111u, 0x22222222u,
                      0x33333333u, 0x44444444u);
}
