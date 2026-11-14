#version 450

#extension GL_KHR_shader_subgroup_basic : require

layout(location = 0) out vec4 out_color;

void main()
{
    uint lane = gl_SubgroupInvocationID;
    out_color = vec4(float(lane & 3u) / 16.0,
                     float((lane >> 2u) & 7u) / 16.0,
                     0.0, 1.0);
}
