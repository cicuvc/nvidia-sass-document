#version 450

#extension GL_ARB_shader_viewport_layer_array : require

void main()
{
    gl_Position = vec4(0.25, 0.5, 0.75, 1.0);
    gl_PointSize = 3.5;
    gl_Layer = 2;
    gl_ViewportIndex = 3;
}
