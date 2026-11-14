#version 450

layout(location = 0) in vec4 vcolor0;
layout(location = 1) in vec4 vcolor1;
layout(location = 0) out vec4 out_color;

void main()
{
    out_color = vcolor0 + vcolor1 * 0.5;
}
