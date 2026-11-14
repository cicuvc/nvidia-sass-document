#version 450

layout(location = 0) in vec4 vcolor;
layout(location = 0) out vec4 out_color;

void main()
{
    vec2 dx = dFdx(vcolor.xy);
    vec2 dy = dFdy(vcolor.zw);
    out_color = vec4(dx, dy);
}
