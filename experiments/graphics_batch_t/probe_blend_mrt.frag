#version 450

layout(location = 0) out vec4 out_color0;
layout(location = 1) out vec4 out_color1;

void main()
{
    out_color0 = vec4(0.25, 0.5, 0.75, 0.5);
    out_color1 = vec4(0.6, 0.3, 0.2, 0.7);
}
