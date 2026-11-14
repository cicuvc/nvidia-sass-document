#version 450

#extension GL_ARB_shader_draw_parameters : require
#extension GL_EXT_multiview : require
#extension GL_EXT_device_group : require

layout(set = 0, binding = 0, std430) buffer BuiltinData {
    uvec4 values[];
} data;

void main()
{
    data.values[0] = uvec4(uint(gl_VertexIndex),
                           uint(gl_InstanceIndex),
                           uint(gl_BaseVertexARB),
                           uint(gl_BaseInstanceARB));
    data.values[1] = uvec4(uint(gl_DrawIDARB), uint(gl_ViewIndex), 0u, 0u);
    data.values[2] = uvec4(uint(gl_DeviceIndex), 0u, 0u, 0u);
    gl_Position = vec4(0.0, 0.0, 0.0, 1.0);
}
