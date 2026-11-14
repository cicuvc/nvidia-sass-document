#version 450

layout(location = 0) out vec4 out_color;

void main()
{
    gl_FragDepth = 0.25;
    out_color = vec4(1.0, 2.0, 3.0, 4.0);
}
