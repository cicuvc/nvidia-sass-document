#version 450

layout(set = 0, binding = 0, std430) buffer VertexData {
    vec4 values[];
} data;

layout(location = 0) out vec4 vcolor;

void main()
{
    uint index = uint(gl_VertexIndex);
    vec4 position = data.values[index];
    data.values[index + 3u] = position;
    gl_Position = position;
    vcolor = vec4(position.xyz, float(index));
}
