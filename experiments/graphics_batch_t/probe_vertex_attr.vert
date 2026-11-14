#version 450

layout(location = 0) in vec4 in_position;
layout(location = 1) in vec4 in_color;
layout(location = 0) out vec4 vcolor;

void main()
{
    gl_Position = in_position;
    vcolor = in_color;
}
