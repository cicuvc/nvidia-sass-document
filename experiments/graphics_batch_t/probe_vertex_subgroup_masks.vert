#version 450

#extension GL_KHR_shader_subgroup_basic : require
#extension GL_KHR_shader_subgroup_ballot : require

layout(set = 0, binding = 0, std430) buffer BuiltinData {
    uvec4 values[];
} data;

void main()
{
    uint index = uint(gl_VertexIndex);
    data.values[index] = gl_SubgroupEqMask;
    data.values[index + 3u] = gl_SubgroupGeMask;
    data.values[index + 6u] = gl_SubgroupGtMask;
    data.values[index + 9u] = gl_SubgroupLeMask;
    data.values[index + 12u] = gl_SubgroupLtMask;
    gl_Position = vec4(0.0, 0.0, 0.0, 1.0);
}
