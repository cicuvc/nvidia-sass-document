#version 450

layout(location = 0) in vec4 vcolor;
layout(location = 0) out vec4 out_color;

void main()
{
    vec4 v = vcolor;
    for (uint k = 0; k < 4; ++k) {
        v = fma(v, vec4(1.25, 0.75, 1.5, 0.625), vec4(float(k)));
        v += vec4(0.125, 0.25, 0.5, 0.0625);
    }
    out_color = v;
}
