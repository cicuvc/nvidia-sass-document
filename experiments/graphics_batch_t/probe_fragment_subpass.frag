#version 450

layout(input_attachment_index = 0, set = 0, binding = 2)
uniform subpassInput input_color;

layout(location = 0) out vec4 out_color;

void main()
{
    out_color = subpassLoad(input_color);
}
