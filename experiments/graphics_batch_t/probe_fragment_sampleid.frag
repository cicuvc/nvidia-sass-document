#version 450

layout(location = 0) out vec4 out_color;

void main()
{
    out_color = vec4(float(gl_SampleID));
}
