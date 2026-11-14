#version 450

layout(location = 0) in vec4 vcolor;
layout(location = 0) out vec4 out_color;

void main()
{
    out_color = interpolateAtSample(vcolor, gl_SampleID);
}
