#version 450

#extension GL_KHR_shader_subgroup_basic : require
#extension GL_NV_shader_sm_builtins : require

layout(location = 0) out uvec4 out_color;

void main()
{
    out_color = uvec4(gl_SubgroupInvocationID,
                      gl_WarpIDNV,
                      gl_SMIDNV,
                      1u);
}
