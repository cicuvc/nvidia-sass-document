#version 450

#extension GL_KHR_shader_subgroup_basic : require
#extension GL_NV_shader_sm_builtins : require

layout(set = 0, binding = 0, std430) buffer BuiltinData {
    uvec4 values[];
} data;

void main()
{
    data.values[gl_VertexIndex] = uvec4(gl_SubgroupInvocationID,
                                       gl_SubgroupSize,
                                       gl_WarpIDNV,
                                       gl_SMIDNV);
    data.values[gl_VertexIndex + 3u] = uvec4(gl_WarpsPerSMNV,
                                             gl_SMCountNV,
                                             0u,
                                             0u);
    gl_Position = vec4(0.0, 0.0, 0.0, 1.0);
}
