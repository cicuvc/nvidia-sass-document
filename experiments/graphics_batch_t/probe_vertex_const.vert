#version 450

layout(location = 0) out vec4 vcolor;

void main()
{
    gl_Position = vec4(1.25, -2.5, 3.75, 1.0);
    vcolor = vec4(4.5, 5.25, 6.75, 7.0);
}
