#version 450

layout(location = 0) in vec4 vcolor;
layout(location = 0) out vec4 out_color;

void main()
{
    vec2 dx = dFdx(vcolor.xy);
    vec2 dy = dFdy(vcolor.xy);
    out_color = vec4(dx.x > 0.0 ? 1.0 : 0.0,
                     dx.y > 0.0 ? 1.0 : 0.0,
                     dy.x > 0.0 ? 1.0 : 0.0,
                     dy.y > 0.0 ? 1.0 : 0.0);
}
