#version 450

layout(location = 0) out vec4 out_color;

void main()
{
    out_color = vec4(gl_SamplePosition, 0.0, 1.0);
}
