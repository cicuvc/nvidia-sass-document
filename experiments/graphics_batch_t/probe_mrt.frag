#version 450

layout(location = 0) out vec4 color0;
layout(location = 1) out vec4 color1;

void main()
{
    color0 = vec4(0.25, 0.5, 0.75, 1.0);
    color1 = vec4(0.125, 0.0625, 0.375, 0.875);
}
