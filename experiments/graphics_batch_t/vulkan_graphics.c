#include <vulkan/vulkan.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CHECK(call)                                                           \
    do {                                                                      \
        VkResult r_ = (call);                                                 \
        if (r_ != VK_SUCCESS) {                                               \
            fprintf(stderr, "%s failed: %d\n", #call, r_);                    \
            exit(1);                                                          \
        }                                                                     \
    } while (0)

static uint32_t find_memory_type(VkPhysicalDevice physical, uint32_t bits,
                                 VkMemoryPropertyFlags props)
{
    VkPhysicalDeviceMemoryProperties mem;
    vkGetPhysicalDeviceMemoryProperties(physical, &mem);
    for (uint32_t i = 0; i < mem.memoryTypeCount; ++i)
        if ((bits & (1u << i)) &&
            (mem.memoryTypes[i].propertyFlags & props) == props)
            return i;
    fprintf(stderr, "no suitable memory type\n");
    exit(1);
}

static uint32_t format_component_count(VkFormat format)
{
    switch (format) {
    case VK_FORMAT_R32G32B32A32_SFLOAT:
    case VK_FORMAT_R32G32B32A32_UINT:
        return 4;
    case VK_FORMAT_R32G32_SFLOAT:
        return 2;
    case VK_FORMAT_R32_SFLOAT:
        return 1;
    default:
        return 0;
    }
}

static VkDeviceSize format_texel_size(VkFormat format)
{
    switch (format) {
    case VK_FORMAT_R32G32B32A32_SFLOAT:
    case VK_FORMAT_R32G32B32A32_UINT:
        return 16;
    case VK_FORMAT_R32G32_SFLOAT:
        return 8;
    case VK_FORMAT_R32_SFLOAT:
    case VK_FORMAT_R8G8B8A8_UNORM:
        return 4;
    default:
        return 0;
    }
}

static VkShaderModule load_shader(VkDevice device, const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) {
        perror(path);
        exit(1);
    }
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    rewind(f);
    uint32_t *code = malloc((size_t)n);
    if (!code || fread(code, 1, (size_t)n, f) != (size_t)n) {
        fprintf(stderr, "failed to read %s\n", path);
        exit(1);
    }
    fclose(f);
    VkShaderModuleCreateInfo info = {
        .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
        .codeSize = (size_t)n,
        .pCode = code,
    };
    VkShaderModule module;
    CHECK(vkCreateShaderModule(device, &info, NULL, &module));
    free(code);
    return module;
}

static int parse_advanced_blend(const char *name, VkBlendOp *op)
{
    static const struct {
        const char *name;
        VkBlendOp op;
    } modes[] = {
        {"multiply", VK_BLEND_OP_MULTIPLY_EXT},
        {"screen", VK_BLEND_OP_SCREEN_EXT},
        {"overlay", VK_BLEND_OP_OVERLAY_EXT},
        {"colordodge", VK_BLEND_OP_COLORDODGE_EXT},
        {"colorburn", VK_BLEND_OP_COLORBURN_EXT},
        {"softlight", VK_BLEND_OP_SOFTLIGHT_EXT},
        {"difference", VK_BLEND_OP_DIFFERENCE_EXT},
        {"exclusion", VK_BLEND_OP_EXCLUSION_EXT},
        {"hsl_hue", VK_BLEND_OP_HSL_HUE_EXT},
        {"hsl_saturation", VK_BLEND_OP_HSL_SATURATION_EXT},
        {"hsl_color", VK_BLEND_OP_HSL_COLOR_EXT},
        {"hsl_luminosity", VK_BLEND_OP_HSL_LUMINOSITY_EXT},
    };
    if (!name)
        return 0;
    for (size_t i = 0; i < sizeof(modes) / sizeof(modes[0]); ++i) {
        if (!strcmp(name, modes[i].name)) {
            *op = modes[i].op;
            return 1;
        }
    }
    return 0;
}

static const char *stage_name(VkShaderStageFlags stages)
{
    if (stages & VK_SHADER_STAGE_VERTEX_BIT)
        return "vertex";
    if (stages & VK_SHADER_STAGE_TESSELLATION_CONTROL_BIT)
        return "tess-control";
    if (stages & VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT)
        return "tess-eval";
    if (stages & VK_SHADER_STAGE_GEOMETRY_BIT)
        return "geometry";
    if (stages & VK_SHADER_STAGE_FRAGMENT_BIT)
        return "fragment";
    if (stages & VK_SHADER_STAGE_COMPUTE_BIT)
        return "compute";
    return "unknown";
}

static void dump_pipeline_executables(VkDevice device, VkPipeline pipeline,
                                      const char *dir)
{
    PFN_vkGetPipelineExecutablePropertiesKHR get_properties =
        (PFN_vkGetPipelineExecutablePropertiesKHR)vkGetDeviceProcAddr(
            device, "vkGetPipelineExecutablePropertiesKHR");
    PFN_vkGetPipelineExecutableInternalRepresentationsKHR get_representations =
        (PFN_vkGetPipelineExecutableInternalRepresentationsKHR)
            vkGetDeviceProcAddr(
                device,
                "vkGetPipelineExecutableInternalRepresentationsKHR");
    if (!get_properties || !get_representations) {
        fprintf(stderr, "pipeline executable property entrypoints unavailable\n");
        return;
    }
    uint32_t executable_count = 0;
    CHECK(get_properties(
        device, &(VkPipelineInfoKHR) {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_INFO_KHR,
            .pipeline = pipeline,
        }, &executable_count, NULL));
    VkPipelineExecutablePropertiesKHR *properties =
        calloc(executable_count, sizeof(*properties));
    for (uint32_t i = 0; i < executable_count; ++i)
        properties[i].sType =
            VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_PROPERTIES_KHR;
    CHECK(get_properties(
        device, &(VkPipelineInfoKHR) {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_INFO_KHR,
            .pipeline = pipeline,
        }, &executable_count, properties));

    for (uint32_t i = 0; i < executable_count; ++i) {
        printf("executable[%u]: stage=%s name=\"%s\" description=\"%s\" "
               "subgroupSize=%u\n",
               i, stage_name(properties[i].stages), properties[i].name,
               properties[i].description, properties[i].subgroupSize);
        VkPipelineExecutableInfoKHR executable_info = {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INFO_KHR,
            .pipeline = pipeline,
            .executableIndex = i,
        };
        uint32_t representation_count = 0;
        CHECK(get_representations(
            device, &executable_info, &representation_count, NULL));
        VkPipelineExecutableInternalRepresentationKHR *representations =
            calloc(representation_count, sizeof(*representations));
        for (uint32_t j = 0; j < representation_count; ++j)
            representations[j].sType =
                VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INTERNAL_REPRESENTATION_KHR;
        CHECK(get_representations(
            device, &executable_info, &representation_count,
            representations));
        for (uint32_t j = 0; j < representation_count; ++j) {
            void *data = malloc(representations[j].dataSize);
            representations[j].pData = data;
            CHECK(get_representations(
                device, &executable_info, &representation_count,
                representations));
            char path[1024];
            snprintf(path, sizeof(path), "%s/executable_%u_%u.%s",
                     dir, i, j,
                     representations[j].isText ? "txt" : "bin");
            FILE *file = fopen(path, "wb");
            if (!file) {
                perror(path);
                exit(1);
            }
            fwrite(representations[j].pData, 1,
                   representations[j].dataSize, file);
            fclose(file);
            printf("  representation[%u]: name=\"%s\" description=\"%s\" "
                   "text=%u size=%zu -> %s\n",
                   j, representations[j].name,
                   representations[j].description,
                   representations[j].isText,
                   representations[j].dataSize, path);
            free(data);
        }
        free(representations);
    }
    free(properties);
}

static void dump_pipeline_binary(VkDevice device, VkPipeline pipeline,
                                 const char *dir)
{
    PFN_vkCreatePipelineBinariesKHR create_binaries =
        (PFN_vkCreatePipelineBinariesKHR)vkGetDeviceProcAddr(
            device, "vkCreatePipelineBinariesKHR");
    PFN_vkGetPipelineBinaryDataKHR get_binary_data =
        (PFN_vkGetPipelineBinaryDataKHR)vkGetDeviceProcAddr(
            device, "vkGetPipelineBinaryDataKHR");
    PFN_vkDestroyPipelineBinaryKHR destroy_binary =
        (PFN_vkDestroyPipelineBinaryKHR)vkGetDeviceProcAddr(
            device, "vkDestroyPipelineBinaryKHR");
    if (!create_binaries || !get_binary_data || !destroy_binary) {
        fprintf(stderr, "pipeline binary entrypoints unavailable\n");
        return;
    }

    VkPipelineBinaryCreateInfoKHR create_info = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_BINARY_CREATE_INFO_KHR,
        .pipeline = pipeline,
    };
    VkPipelineBinaryHandlesInfoKHR handles_info = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_BINARY_HANDLES_INFO_KHR,
    };
    VkResult result = create_binaries(
        device, &create_info, NULL, &handles_info);
    if (result != VK_SUCCESS && result != VK_INCOMPLETE) {
        fprintf(stderr, "vkCreatePipelineBinariesKHR enumerate failed: %d\n",
                result);
        return;
    }
    printf("pipeline binary count=%u\n", handles_info.pipelineBinaryCount);
    if (!handles_info.pipelineBinaryCount)
        return;
    handles_info.pPipelineBinaries = calloc(
        handles_info.pipelineBinaryCount,
        sizeof(*handles_info.pPipelineBinaries));
    result = create_binaries(device, &create_info, NULL, &handles_info);
    if (result != VK_SUCCESS) {
        fprintf(stderr, "vkCreatePipelineBinariesKHR create failed: %d\n",
                result);
        free(handles_info.pPipelineBinaries);
        return;
    }

    for (uint32_t i = 0; i < handles_info.pipelineBinaryCount; ++i) {
        VkPipelineBinaryDataInfoKHR data_info = {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_BINARY_DATA_INFO_KHR,
            .pipelineBinary = handles_info.pPipelineBinaries[i],
        };
        VkPipelineBinaryKeyKHR key = {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_BINARY_KEY_KHR,
        };
        size_t data_size = 0;
        result = get_binary_data(
            device, &data_info, &key, &data_size, NULL);
        if (result != VK_SUCCESS && result != VK_INCOMPLETE) {
            fprintf(stderr, "vkGetPipelineBinaryDataKHR size failed: %d\n",
                    result);
            continue;
        }
        void *data = malloc(data_size);
        result = get_binary_data(
            device, &data_info, &key, &data_size, data);
        if (result != VK_SUCCESS) {
            fprintf(stderr, "vkGetPipelineBinaryDataKHR data failed: %d\n",
                    result);
            free(data);
            continue;
        }
        char path[1024];
        snprintf(path, sizeof(path), "%s/pipeline_binary_%u.bin", dir, i);
        FILE *file = fopen(path, "wb");
        if (!file) {
            perror(path);
            free(data);
            exit(1);
        }
        fwrite(data, 1, data_size, file);
        fclose(file);
        printf("pipeline binary[%u]: size=%zu keySize=%u key=",
               i, data_size, key.keySize);
        for (uint32_t j = 0; j < key.keySize; ++j)
            printf("%02x", key.key[j]);
        printf(" -> %s\n", path);
        free(data);
        destroy_binary(device, handles_info.pPipelineBinaries[i], NULL);
    }
    free(handles_info.pPipelineBinaries);
}

int main(int argc, char **argv)
{
    if (argc != 3 && argc != 4) {
        fprintf(stderr, "usage: %s vertex.spv fragment.spv [geometry.spv]\n",
                argv[0]);
        return 2;
    }

    VkApplicationInfo app = {
        .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "graphics-batch-t-probe",
        .apiVersion = VK_API_VERSION_1_4,
    };
    VkInstanceCreateInfo ii = {
        .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &app,
    };
    VkInstance instance;
    CHECK(vkCreateInstance(&ii, NULL, &instance));

    uint32_t count = 0;
    CHECK(vkEnumeratePhysicalDevices(instance, &count, NULL));
    VkPhysicalDevice *devices = calloc(count, sizeof(*devices));
    CHECK(vkEnumeratePhysicalDevices(instance, &count, devices));
    const char *want_gpu = getenv("PROBE_GPU_NAME");
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    uint32_t qf = UINT32_MAX;
    int has_advanced_blend = 0;
    int has_pipeline_executables = 0;
    int has_pipeline_binary = 0;
    for (uint32_t i = 0; i < count; ++i) {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(devices[i], &props);
        if (want_gpu && !strstr(props.deviceName, want_gpu))
            continue;
        uint32_t n = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(devices[i], &n, NULL);
        VkQueueFamilyProperties *qprops = calloc(n, sizeof(*qprops));
        vkGetPhysicalDeviceQueueFamilyProperties(devices[i], &n, qprops);
        for (uint32_t j = 0; j < n; ++j)
            if (qprops[j].queueFlags & VK_QUEUE_GRAPHICS_BIT) {
                qf = j;
                break;
            }
        free(qprops);
        if (qf != UINT32_MAX) {
            physical = devices[i];
            uint32_t extension_count = 0;
            vkEnumerateDeviceExtensionProperties(physical, NULL,
                                                 &extension_count, NULL);
            VkExtensionProperties *extensions =
                calloc(extension_count, sizeof(*extensions));
            vkEnumerateDeviceExtensionProperties(
                physical, NULL, &extension_count, extensions);
            for (uint32_t j = 0; j < extension_count; ++j) {
                if (!strcmp(extensions[j].extensionName,
                            VK_EXT_BLEND_OPERATION_ADVANCED_EXTENSION_NAME))
                    has_advanced_blend = 1;
                if (!strcmp(extensions[j].extensionName,
                            VK_KHR_PIPELINE_EXECUTABLE_PROPERTIES_EXTENSION_NAME))
                    has_pipeline_executables = 1;
                if (!strcmp(extensions[j].extensionName,
                            VK_KHR_PIPELINE_BINARY_EXTENSION_NAME))
                    has_pipeline_binary = 1;
            }
            free(extensions);
            printf("GPU: %s\n", props.deviceName);
            break;
        }
    }
    if (physical == VK_NULL_HANDLE) {
        fprintf(stderr, "no matching graphics GPU\n");
        return 1;
    }

    float priority = 1.0f;
    const char *blend_mode = getenv("PROBE_BLEND");
    const char *executable_dir = getenv("PROBE_EXECUTABLE_DIR");
    const char *binary_dir = getenv("PROBE_PIPELINE_BINARY_DIR");
    int fragment_bindless = getenv("PROBE_FRAGMENT_BINDLESS") != NULL;
    int fragment_image_bindless =
        getenv("PROBE_FRAGMENT_IMAGE_BINDLESS") != NULL;
    int fragment_barycentric =
        getenv("PROBE_FRAGMENT_BARYCENTRIC") != NULL;
    int fragment_footprint =
        getenv("PROBE_FRAGMENT_FOOTPRINT") != NULL;
    int fragment_coverage =
        getenv("PROBE_FRAGMENT_COVERAGE") != NULL;
    int vertex_xfb = getenv("PROBE_VERTEX_XFB") != NULL;
    const char *mesh_path = getenv("PROBE_MESH_SHADER");
    int mesh_shader = mesh_path != NULL;
    uint32_t sample_count = 1;
    const char *sample_count_env = getenv("PROBE_SAMPLES");
    if (sample_count_env)
        sample_count = (uint32_t)strtoul(sample_count_env, NULL, 0);
    VkSampleCountFlagBits sample_flags = VK_SAMPLE_COUNT_1_BIT;
    switch (sample_count) {
    case 1: sample_flags = VK_SAMPLE_COUNT_1_BIT; break;
    case 2: sample_flags = VK_SAMPLE_COUNT_2_BIT; break;
    case 4: sample_flags = VK_SAMPLE_COUNT_4_BIT; break;
    case 8: sample_flags = VK_SAMPLE_COUNT_8_BIT; break;
    default:
        fprintf(stderr, "PROBE_SAMPLES must be 1, 2, 4, or 8\n");
        return 1;
    }
    VkBlendOp advanced_blend_op = VK_BLEND_OP_ADD;
    int advanced_blend =
        parse_advanced_blend(blend_mode, &advanced_blend_op);
    if (advanced_blend && !has_advanced_blend) {
        fprintf(stderr, "GPU lacks %s\n",
                VK_EXT_BLEND_OPERATION_ADVANCED_EXTENSION_NAME);
        return 1;
    }
    if (executable_dir && !has_pipeline_executables) {
        fprintf(stderr, "GPU lacks %s\n",
                VK_KHR_PIPELINE_EXECUTABLE_PROPERTIES_EXTENSION_NAME);
        return 1;
    }
    if (binary_dir && !has_pipeline_binary) {
        fprintf(stderr, "GPU lacks %s\n",
                VK_KHR_PIPELINE_BINARY_EXTENSION_NAME);
        return 1;
    }
    VkPhysicalDevicePipelineBinaryFeaturesKHR pipeline_binary_features = {
        .sType =
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_BINARY_FEATURES_KHR,
    };
    VkPhysicalDeviceDescriptorIndexingFeatures descriptor_indexing = {
        .sType =
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_FEATURES,
    };
    VkPhysicalDeviceFragmentShaderBarycentricFeaturesKHR barycentric_features = {
        .sType =
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FRAGMENT_SHADER_BARYCENTRIC_FEATURES_KHR,
    };
    VkPhysicalDeviceShaderImageFootprintFeaturesNV footprint_features = {
        .sType =
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_IMAGE_FOOTPRINT_FEATURES_NV,
    };
    VkPhysicalDeviceTransformFeedbackFeaturesEXT transform_feedback_features = {
        .sType =
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_TRANSFORM_FEEDBACK_FEATURES_EXT,
    };
    VkPhysicalDeviceMeshShaderFeaturesEXT mesh_shader_features = {
        .sType =
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MESH_SHADER_FEATURES_EXT,
    };
    VkPhysicalDeviceFeatures enabled_features = {0};
    VkPhysicalDeviceFeatures2 supported_features = {
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
        .pNext = &descriptor_indexing,
    };
    if (fragment_bindless || fragment_image_bindless)
        vkGetPhysicalDeviceFeatures2(physical, &supported_features);
    if (binary_dir) {
        VkPhysicalDeviceFeatures2 features = {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
            .pNext = &pipeline_binary_features,
        };
        vkGetPhysicalDeviceFeatures2(physical, &features);
        if (!pipeline_binary_features.pipelineBinaries) {
            fprintf(stderr, "pipelineBinaries feature unavailable\n");
            return 1;
        }
    }
    if (fragment_bindless) {
        if (!supported_features.features.shaderSampledImageArrayDynamicIndexing ||
            !descriptor_indexing.shaderSampledImageArrayNonUniformIndexing) {
            fprintf(stderr,
                    "sampled image dynamic/nonuniform indexing unavailable\n");
            return 1;
        }
        enabled_features.shaderSampledImageArrayDynamicIndexing = VK_TRUE;
        descriptor_indexing.shaderSampledImageArrayNonUniformIndexing =
            VK_TRUE;
    }
    if (fragment_image_bindless) {
        if (!supported_features.features.shaderStorageImageArrayDynamicIndexing ||
            !descriptor_indexing.shaderStorageImageArrayNonUniformIndexing) {
            fprintf(stderr,
                    "storage image dynamic/nonuniform indexing unavailable\n");
            return 1;
        }
        enabled_features.shaderStorageImageArrayDynamicIndexing = VK_TRUE;
        descriptor_indexing.shaderStorageImageArrayNonUniformIndexing =
            VK_TRUE;
    }
    if (fragment_barycentric) {
        VkPhysicalDeviceFeatures2 features = {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
            .pNext = &barycentric_features,
        };
        vkGetPhysicalDeviceFeatures2(physical, &features);
        if (!barycentric_features.fragmentShaderBarycentric) {
            fprintf(stderr,
                    "fragment shader barycentric feature unavailable\n");
            return 1;
        }
        barycentric_features.fragmentShaderBarycentric = VK_TRUE;
    }
    if (fragment_footprint) {
        VkPhysicalDeviceFeatures2 features = {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
            .pNext = &footprint_features,
        };
        vkGetPhysicalDeviceFeatures2(physical, &features);
        if (!footprint_features.imageFootprint) {
            fprintf(stderr, "imageFootprint feature unavailable\n");
            return 1;
        }
        footprint_features.imageFootprint = VK_TRUE;
    }
    if (vertex_xfb) {
        VkPhysicalDeviceFeatures2 features = {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
            .pNext = &transform_feedback_features,
        };
        vkGetPhysicalDeviceFeatures2(physical, &features);
        if (!transform_feedback_features.transformFeedback) {
            fprintf(stderr,
                    "transformFeedback feature unavailable\n");
            return 1;
        }
        transform_feedback_features.transformFeedback = VK_TRUE;
    }
    if (mesh_shader) {
        VkPhysicalDeviceFeatures2 features = {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
            .pNext = &mesh_shader_features,
        };
        vkGetPhysicalDeviceFeatures2(physical, &features);
        if (!mesh_shader_features.meshShader) {
            fprintf(stderr, "meshShader feature unavailable\n");
            return 1;
        }
        mesh_shader_features.meshShader = VK_TRUE;
    }
    const void *feature_tail = NULL;
    if (mesh_shader) {
        mesh_shader_features.pNext = (void *)feature_tail;
        feature_tail = &mesh_shader_features;
    }
    if (vertex_xfb) {
        transform_feedback_features.pNext = (void *)feature_tail;
        feature_tail = &transform_feedback_features;
    }
    if (fragment_footprint) {
        footprint_features.pNext = (void *)feature_tail;
        feature_tail = &footprint_features;
    }
    if (fragment_barycentric) {
        barycentric_features.pNext = (void *)feature_tail;
        feature_tail = &barycentric_features;
    }
    if (fragment_bindless) {
        descriptor_indexing.pNext = (void *)feature_tail;
        feature_tail = &descriptor_indexing;
    }
    pipeline_binary_features.pNext = (void *)feature_tail;
    VkDeviceQueueCreateInfo qi = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = qf,
        .queueCount = 1,
        .pQueuePriorities = &priority,
    };
    VkDeviceCreateInfo di = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1,
        .pQueueCreateInfos = &qi,
        .pNext = binary_dir
                     ? (const void *)&pipeline_binary_features
                     : feature_tail,
        .pEnabledFeatures =
            fragment_bindless ? &enabled_features : NULL,
    };
    const char *enabled_extensions[8];
    uint32_t enabled_extension_count = 0;
    if (advanced_blend) {
        enabled_extensions[enabled_extension_count++] =
            VK_EXT_BLEND_OPERATION_ADVANCED_EXTENSION_NAME;
    }
    if (executable_dir)
        enabled_extensions[enabled_extension_count++] =
            VK_KHR_PIPELINE_EXECUTABLE_PROPERTIES_EXTENSION_NAME;
    if (binary_dir)
        enabled_extensions[enabled_extension_count++] =
            VK_KHR_PIPELINE_BINARY_EXTENSION_NAME;
    if (fragment_barycentric)
        enabled_extensions[enabled_extension_count++] =
            VK_KHR_FRAGMENT_SHADER_BARYCENTRIC_EXTENSION_NAME;
    if (fragment_footprint)
        enabled_extensions[enabled_extension_count++] =
            VK_NV_SHADER_IMAGE_FOOTPRINT_EXTENSION_NAME;
    if (fragment_coverage)
        enabled_extensions[enabled_extension_count++] =
            VK_EXT_CONSERVATIVE_RASTERIZATION_EXTENSION_NAME;
    if (vertex_xfb)
        enabled_extensions[enabled_extension_count++] =
            VK_EXT_TRANSFORM_FEEDBACK_EXTENSION_NAME;
    if (mesh_shader)
        enabled_extensions[enabled_extension_count++] =
            VK_EXT_MESH_SHADER_EXTENSION_NAME;
    di.enabledExtensionCount = enabled_extension_count;
    di.ppEnabledExtensionNames =
        enabled_extension_count ? enabled_extensions : NULL;
    VkDevice device;
    CHECK(vkCreateDevice(physical, &di, NULL, &device));
    VkQueue queue;
    vkGetDeviceQueue(device, qf, 0, &queue);

    enum { MAX_COLOR_TARGETS = 8 };
    uint32_t color_targets = 1;
    const char *color_targets_env = getenv("PROBE_COLOR_TARGETS");
    if (color_targets_env)
        color_targets = (uint32_t)strtoul(color_targets_env, NULL, 0);
    if (color_targets < 1 || color_targets > MAX_COLOR_TARGETS) {
        fprintf(stderr, "PROBE_COLOR_TARGETS must be in 1..%d\n",
                MAX_COLOR_TARGETS);
        return 1;
    }

    int uint_color = getenv("PROBE_UINT_COLOR") != NULL;
    int readback = getenv("PROBE_READBACK") != NULL;
    int vertex_only = getenv("PROBE_VERTEX_ONLY") != NULL;
    int vertex_input = getenv("PROBE_VERTEX_INPUT") != NULL;
    int vertex_ssbo = getenv("PROBE_VERTEX_SSBO") != NULL;
    int fragment_texture = getenv("PROBE_FRAGMENT_TEXTURE") != NULL;
    int fragment_image = getenv("PROBE_FRAGMENT_IMAGE") != NULL;
    if (fragment_image_bindless)
        fragment_image = 1;
    int fragment_subpass = getenv("PROBE_FRAGMENT_SUBPASS") != NULL;
    int mixed_outputs = getenv("PROBE_MIXED_OUTPUTS") != NULL;
    int depth_output = getenv("PROBE_DEPTH_OUTPUT") != NULL;
    if (fragment_subpass)
        color_targets = 2;
    if (mixed_outputs)
        color_targets = 8;
    VkFormat format = uint_color ? VK_FORMAT_R32G32B32A32_UINT
                                 : VK_FORMAT_R8G8B8A8_UNORM;
    VkFormat color_formats[MAX_COLOR_TARGETS] = {0};
    uint32_t color_components[MAX_COLOR_TARGETS] = {0};
    VkImage images[MAX_COLOR_TARGETS] = {0};
    VkDeviceMemory image_memories[MAX_COLOR_TARGETS] = {0};
    VkImageView views[MAX_COLOR_TARGETS] = {0};
    VkImageView framebuffer_views[MAX_COLOR_TARGETS + 1] = {0};
    VkAttachmentDescription attachments[MAX_COLOR_TARGETS + 1] = {0};
    VkAttachmentReference color_refs[MAX_COLOR_TARGETS] = {0};
    for (uint32_t i = 0; i < color_targets; ++i) {
        static const VkFormat mixed_formats[] = {
            VK_FORMAT_R32G32B32A32_SFLOAT,
            VK_FORMAT_R32G32_SFLOAT,
            VK_FORMAT_R32_SFLOAT,
            VK_FORMAT_R32G32B32A32_SFLOAT,
            VK_FORMAT_R32G32_SFLOAT,
            VK_FORMAT_R32_SFLOAT,
            VK_FORMAT_R32G32B32A32_SFLOAT,
            VK_FORMAT_R32G32_SFLOAT,
        };
        color_formats[i] = mixed_outputs ? mixed_formats[i] : format;
        color_components[i] = format_component_count(color_formats[i]);
        VkImageCreateInfo image_info = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
            .imageType = VK_IMAGE_TYPE_2D,
            .format = color_formats[i],
            .extent = {64, 64, 1},
            .mipLevels = 1,
            .arrayLayers = 1,
            .samples = sample_flags,
            .tiling = VK_IMAGE_TILING_OPTIMAL,
            .usage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT |
                     VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        };
        CHECK(vkCreateImage(device, &image_info, NULL, &images[i]));
        VkMemoryRequirements image_req;
        vkGetImageMemoryRequirements(device, images[i], &image_req);
        VkMemoryAllocateInfo image_alloc = {
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .allocationSize = image_req.size,
            .memoryTypeIndex = find_memory_type(
                physical, image_req.memoryTypeBits,
                VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT),
        };
        CHECK(vkAllocateMemory(device, &image_alloc, NULL,
                               &image_memories[i]));
        CHECK(vkBindImageMemory(device, images[i], image_memories[i], 0));
        VkImageViewCreateInfo view_info = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
            .image = images[i],
            .viewType = VK_IMAGE_VIEW_TYPE_2D,
            .format = color_formats[i],
            .subresourceRange = {
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .levelCount = 1,
                .layerCount = 1,
            },
        };
        CHECK(vkCreateImageView(device, &view_info, NULL, &views[i]));
        framebuffer_views[i] = views[i];
        attachments[i] = (VkAttachmentDescription) {
            .format = color_formats[i],
            .samples = sample_flags,
            .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
            .storeOp = VK_ATTACHMENT_STORE_OP_STORE,
            .stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE,
            .stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE,
            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
            .finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
        };
        color_refs[i] = (VkAttachmentReference) {
            .attachment = i,
            .layout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
        };
    }
    VkImage depth_image = VK_NULL_HANDLE;
    VkDeviceMemory depth_image_memory = VK_NULL_HANDLE;
    VkImageView depth_view = VK_NULL_HANDLE;
    VkAttachmentReference depth_ref = {0};
    if (depth_output) {
        VkImageCreateInfo image_info = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
            .imageType = VK_IMAGE_TYPE_2D,
            .format = VK_FORMAT_D32_SFLOAT,
            .extent = {64, 64, 1},
            .mipLevels = 1,
            .arrayLayers = 1,
            .samples = sample_flags,
            .tiling = VK_IMAGE_TILING_OPTIMAL,
            .usage = VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT |
                     VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        };
        CHECK(vkCreateImage(device, &image_info, NULL, &depth_image));
        VkMemoryRequirements image_req;
        vkGetImageMemoryRequirements(device, depth_image, &image_req);
        VkMemoryAllocateInfo image_alloc = {
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .allocationSize = image_req.size,
            .memoryTypeIndex = find_memory_type(
                physical, image_req.memoryTypeBits,
                VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT),
        };
        CHECK(vkAllocateMemory(device, &image_alloc, NULL,
                               &depth_image_memory));
        CHECK(vkBindImageMemory(
            device, depth_image, depth_image_memory, 0));
        VkImageViewCreateInfo view_info = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
            .image = depth_image,
            .viewType = VK_IMAGE_VIEW_TYPE_2D,
            .format = VK_FORMAT_D32_SFLOAT,
            .subresourceRange = {
                .aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT,
                .levelCount = 1,
                .layerCount = 1,
            },
        };
        CHECK(vkCreateImageView(device, &view_info, NULL, &depth_view));
        framebuffer_views[color_targets] = depth_view;
        attachments[color_targets] = (VkAttachmentDescription) {
            .format = VK_FORMAT_D32_SFLOAT,
            .samples = sample_flags,
            .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
            .storeOp = VK_ATTACHMENT_STORE_OP_STORE,
            .stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE,
            .stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE,
            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
            .finalLayout =
                VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL,
        };
        depth_ref = (VkAttachmentReference) {
            .attachment = color_targets,
            .layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL,
        };
    }
    VkAttachmentReference input_ref = {
        .attachment = 0,
        .layout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
    };
    VkSubpassDescription subpasses[2] = {
        {
            .pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS,
            .colorAttachmentCount = fragment_subpass ? 1u : color_targets,
            .pColorAttachments = &color_refs[0],
            .pDepthStencilAttachment = depth_output ? &depth_ref : NULL,
        },
        {
            .pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS,
            .inputAttachmentCount = 1,
            .pInputAttachments = &input_ref,
            .colorAttachmentCount = 1,
            .pColorAttachments = &color_refs[1],
        },
    };
    VkSubpassDependency subpass_dependency = {
        .srcSubpass = 0,
        .dstSubpass = 1,
        .srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
        .dstStageMask = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,
        .srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
        .dstAccessMask = VK_ACCESS_INPUT_ATTACHMENT_READ_BIT,
        .dependencyFlags = VK_DEPENDENCY_BY_REGION_BIT,
    };
    VkRenderPassCreateInfo rp_info = {
        .sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
        .attachmentCount = color_targets + (depth_output ? 1u : 0u),
        .pAttachments = attachments,
        .subpassCount = fragment_subpass ? 2u : 1u,
        .pSubpasses = subpasses,
        .dependencyCount = fragment_subpass ? 1u : 0u,
        .pDependencies = fragment_subpass ? &subpass_dependency : NULL,
    };
    VkRenderPass renderpass;
    CHECK(vkCreateRenderPass(device, &rp_info, NULL, &renderpass));
    VkFramebufferCreateInfo fb_info = {
        .sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,
        .renderPass = renderpass,
        .attachmentCount = color_targets + (depth_output ? 1u : 0u),
        .pAttachments = framebuffer_views,
        .width = 64,
        .height = 64,
        .layers = 1,
    };
    VkFramebuffer framebuffer;
    CHECK(vkCreateFramebuffer(device, &fb_info, NULL, &framebuffer));

    VkShaderModule vert = load_shader(device, argv[1]);
    VkShaderModule frag =
        vertex_only ? VK_NULL_HANDLE : load_shader(device, argv[2]);
    VkShaderModule geom = VK_NULL_HANDLE;
    VkShaderModule tesc = VK_NULL_HANDLE;
    VkShaderModule tese = VK_NULL_HANDLE;
    VkShaderModule mesh = VK_NULL_HANDLE;
    const char *tesc_path = getenv("PROBE_TCS");
    const char *tese_path = getenv("PROBE_TES");
    int tessellation = tesc_path && tese_path;
    VkPipelineShaderStageCreateInfo stages[5] = {
        {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_VERTEX_BIT,
            .module = vert,
            .pName = "main",
        },
        {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_FRAGMENT_BIT,
            .module = frag,
            .pName = "main",
        },
    };
    if (argc == 4 && !mesh_shader) {
        geom = load_shader(device, argv[3]);
        stages[2] = (VkPipelineShaderStageCreateInfo) {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_GEOMETRY_BIT,
            .module = geom,
            .pName = "main",
        };
    }
    uint32_t stage_count = mesh_shader ? 1u : vertex_only ? 1u : 2u;
    if (argc == 4 && !mesh_shader)
        ++stage_count;
    if (mesh_shader) {
        mesh = load_shader(device, mesh_path);
        stages[0] = (VkPipelineShaderStageCreateInfo) {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_MESH_BIT_EXT,
            .module = mesh,
            .pName = "main",
        };
    }
    if (tessellation && !mesh_shader) {
        tesc = load_shader(device, tesc_path);
        tese = load_shader(device, tese_path);
        stages[stage_count++] = (VkPipelineShaderStageCreateInfo) {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_TESSELLATION_CONTROL_BIT,
            .module = tesc,
            .pName = "main",
        };
        stages[stage_count++] = (VkPipelineShaderStageCreateInfo) {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT,
            .module = tese,
            .pName = "main",
        };
    }
    VkVertexInputBindingDescription vertex_binding = {
        .binding = 0,
        .stride = 32,
        .inputRate = VK_VERTEX_INPUT_RATE_VERTEX,
    };
    VkVertexInputAttributeDescription vertex_attributes[2] = {
        {
            .location = 0,
            .binding = 0,
            .format = VK_FORMAT_R32G32B32A32_SFLOAT,
            .offset = 0,
        },
        {
            .location = 1,
            .binding = 0,
            .format = VK_FORMAT_R32G32B32A32_SFLOAT,
            .offset = 16,
        },
    };
    VkPipelineVertexInputStateCreateInfo vertex_input_state = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO,
        .vertexBindingDescriptionCount = vertex_input ? 1u : 0u,
        .pVertexBindingDescriptions =
            vertex_input ? &vertex_binding : NULL,
        .vertexAttributeDescriptionCount = vertex_input ? 2u : 0u,
        .pVertexAttributeDescriptions =
            vertex_input ? vertex_attributes : NULL,
    };
    VkPipelineInputAssemblyStateCreateInfo input_assembly = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
        .topology = tessellation
                        ? VK_PRIMITIVE_TOPOLOGY_PATCH_LIST
                        : VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
    };
    VkViewport viewport = {0, 0, 64, 64, 0, 1};
    VkRect2D scissor = {{0, 0}, {64, 64}};
    VkPipelineViewportStateCreateInfo viewport_state = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
        .viewportCount = 1,
        .pViewports = &viewport,
        .scissorCount = 1,
        .pScissors = &scissor,
    };
    VkPipelineRasterizationStateCreateInfo raster = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
        .polygonMode = VK_POLYGON_MODE_FILL,
        .cullMode = VK_CULL_MODE_NONE,
        .frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE,
        .lineWidth = 1.0f,
        .rasterizerDiscardEnable = vertex_only ? VK_TRUE : VK_FALSE,
    };
    VkPipelineRasterizationConservativeStateCreateInfoEXT conservative = {
        .sType =
            VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_CONSERVATIVE_STATE_CREATE_INFO_EXT,
        .conservativeRasterizationMode =
            VK_CONSERVATIVE_RASTERIZATION_MODE_UNDERESTIMATE_EXT,
    };
    if (fragment_coverage)
        raster.pNext = &conservative;
    VkPipelineMultisampleStateCreateInfo ms = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
        .rasterizationSamples = sample_flags,
        .sampleShadingEnable =
            getenv("PROBE_SAMPLE_SHADING") ? VK_TRUE : VK_FALSE,
        .minSampleShading = 1.0f,
    };
    VkPipelineDepthStencilStateCreateInfo depth_stencil = {
        .sType =
            VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO,
        .depthTestEnable = depth_output ? VK_TRUE : VK_FALSE,
        .depthWriteEnable = depth_output ? VK_TRUE : VK_FALSE,
        .depthCompareOp = VK_COMPARE_OP_ALWAYS,
        .depthBoundsTestEnable = VK_FALSE,
        .stencilTestEnable = VK_FALSE,
    };
    VkPipelineColorBlendAttachmentState blend_attachments[MAX_COLOR_TARGETS] = {
        0
    };
    for (uint32_t i = 0; i < color_targets; ++i) {
        blend_attachments[i].colorWriteMask = 0xf;
        if (!blend_mode)
            continue;
        blend_attachments[i].blendEnable = VK_TRUE;
        blend_attachments[i].srcColorBlendFactor = VK_BLEND_FACTOR_ONE;
        blend_attachments[i].dstColorBlendFactor = VK_BLEND_FACTOR_ZERO;
        blend_attachments[i].colorBlendOp = VK_BLEND_OP_ADD;
        blend_attachments[i].srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
        blend_attachments[i].dstAlphaBlendFactor = VK_BLEND_FACTOR_ZERO;
        blend_attachments[i].alphaBlendOp = VK_BLEND_OP_ADD;
        if (advanced_blend) {
            blend_attachments[i].colorBlendOp = advanced_blend_op;
            blend_attachments[i].alphaBlendOp = advanced_blend_op;
        } else if (!strcmp(blend_mode, "alpha") ||
            (!strcmp(blend_mode, "mixed_mrt") && i == 0)) {
            blend_attachments[i].srcColorBlendFactor =
                VK_BLEND_FACTOR_SRC_ALPHA;
            blend_attachments[i].dstColorBlendFactor =
                VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
            blend_attachments[i].dstAlphaBlendFactor =
                VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
        } else if (!strcmp(blend_mode, "add") ||
                   (!strcmp(blend_mode, "mixed_mrt") && i == 1)) {
            blend_attachments[i].srcColorBlendFactor = VK_BLEND_FACTOR_ONE;
            blend_attachments[i].dstColorBlendFactor = VK_BLEND_FACTOR_ONE;
            blend_attachments[i].srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
            blend_attachments[i].dstAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
        } else if (!strcmp(blend_mode, "sub") ||
                   !strcmp(blend_mode, "rsub") ||
                   !strcmp(blend_mode, "min") ||
                   !strcmp(blend_mode, "max")) {
            blend_attachments[i].srcColorBlendFactor = VK_BLEND_FACTOR_ONE;
            blend_attachments[i].dstColorBlendFactor = VK_BLEND_FACTOR_ONE;
            blend_attachments[i].srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
            blend_attachments[i].dstAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
            if (!strcmp(blend_mode, "sub")) {
                blend_attachments[i].colorBlendOp = VK_BLEND_OP_SUBTRACT;
                blend_attachments[i].alphaBlendOp = VK_BLEND_OP_SUBTRACT;
            } else if (!strcmp(blend_mode, "rsub")) {
                blend_attachments[i].colorBlendOp =
                    VK_BLEND_OP_REVERSE_SUBTRACT;
                blend_attachments[i].alphaBlendOp =
                    VK_BLEND_OP_REVERSE_SUBTRACT;
            } else if (!strcmp(blend_mode, "min")) {
                blend_attachments[i].colorBlendOp = VK_BLEND_OP_MIN;
                blend_attachments[i].alphaBlendOp = VK_BLEND_OP_MIN;
            } else {
                blend_attachments[i].colorBlendOp = VK_BLEND_OP_MAX;
                blend_attachments[i].alphaBlendOp = VK_BLEND_OP_MAX;
            }
        } else if (!strcmp(blend_mode, "srccolor")) {
            blend_attachments[i].srcColorBlendFactor =
                VK_BLEND_FACTOR_SRC_COLOR;
            blend_attachments[i].dstColorBlendFactor =
                VK_BLEND_FACTOR_ONE_MINUS_SRC_COLOR;
        } else if (!strcmp(blend_mode, "dstcolor")) {
            blend_attachments[i].srcColorBlendFactor =
                VK_BLEND_FACTOR_DST_COLOR;
            blend_attachments[i].dstColorBlendFactor =
                VK_BLEND_FACTOR_ONE_MINUS_DST_COLOR;
        } else if (!strcmp(blend_mode, "saturate")) {
            blend_attachments[i].srcColorBlendFactor =
                VK_BLEND_FACTOR_SRC_ALPHA_SATURATE;
            blend_attachments[i].dstColorBlendFactor =
                VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
        } else {
            fprintf(stderr, "unknown PROBE_BLEND mode: %s\n", blend_mode);
            return 1;
        }
    }
    VkPipelineColorBlendAdvancedStateCreateInfoEXT blend_advanced = {
        .sType =
            VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_ADVANCED_STATE_CREATE_INFO_EXT,
        .blendOverlap = VK_BLEND_OVERLAP_UNCORRELATED_EXT,
    };
    VkPipelineColorBlendStateCreateInfo blend = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
        .pNext = advanced_blend ? &blend_advanced : NULL,
        .attachmentCount = color_targets,
        .pAttachments = blend_attachments,
    };
    VkDescriptorSetLayout descriptor_layout = VK_NULL_HANDLE;
    VkDescriptorSetLayoutBinding descriptor_bindings[3] = {0};
    uint32_t descriptor_binding_count = 0;
    if (vertex_ssbo) {
        descriptor_bindings[descriptor_binding_count++] =
            (VkDescriptorSetLayoutBinding) {
            .binding = 0,
            .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
            .descriptorCount = 1,
            .stageFlags = VK_SHADER_STAGE_VERTEX_BIT,
        };
    }
    if (fragment_texture || fragment_bindless || fragment_footprint) {
        descriptor_bindings[descriptor_binding_count++] =
            (VkDescriptorSetLayoutBinding) {
            .binding = 0,
            .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
            .descriptorCount = fragment_bindless ? 8u : 1u,
            .stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT,
        };
    }
    if (fragment_image) {
        descriptor_bindings[descriptor_binding_count++] =
            (VkDescriptorSetLayoutBinding) {
            .binding = 1,
            .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,
            .descriptorCount = fragment_image_bindless ? 8u : 1u,
            .stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT,
        };
    }
    if (fragment_subpass) {
        descriptor_bindings[descriptor_binding_count++] =
            (VkDescriptorSetLayoutBinding) {
            .binding = 2,
            .descriptorType = VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT,
            .descriptorCount = 1,
            .stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT,
        };
    }
    if (descriptor_binding_count) {
        VkDescriptorSetLayoutCreateInfo descriptor_layout_info = {
            .sType =
                VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
            .bindingCount = descriptor_binding_count,
            .pBindings = descriptor_bindings,
        };
        CHECK(vkCreateDescriptorSetLayout(
            device, &descriptor_layout_info, NULL, &descriptor_layout));
    }
    VkPipelineLayoutCreateInfo pl_info = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .setLayoutCount = descriptor_binding_count ? 1u : 0u,
        .pSetLayouts = descriptor_binding_count ? &descriptor_layout : NULL,
    };
    VkPipelineLayout layout;
    CHECK(vkCreatePipelineLayout(device, &pl_info, NULL, &layout));
    VkPipelineTessellationStateCreateInfo tessellation_state = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_TESSELLATION_STATE_CREATE_INFO,
        .patchControlPoints = 3,
    };
    VkGraphicsPipelineCreateInfo gp_info = {
        .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
        .stageCount = stage_count,
        .pStages = stages,
        .pVertexInputState = &vertex_input_state,
        .pInputAssemblyState = &input_assembly,
        .pTessellationState =
            tessellation ? &tessellation_state : NULL,
        .pViewportState = &viewport_state,
        .pRasterizationState = &raster,
        .pMultisampleState = &ms,
        .pDepthStencilState = &depth_stencil,
        .pColorBlendState = &blend,
        .layout = layout,
        .renderPass = renderpass,
    };
    VkPipelineCreateFlags2CreateInfoKHR capture_flags = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_CREATE_FLAGS_2_CREATE_INFO_KHR,
        .flags = VK_PIPELINE_CREATE_2_CAPTURE_DATA_BIT_KHR,
    };
    if (binary_dir)
        gp_info.pNext = &capture_flags;
    VkPipeline pipeline;
    CHECK(vkCreateGraphicsPipelines(device, VK_NULL_HANDLE, 1, &gp_info,
                                    NULL, &pipeline));
    if (executable_dir)
        dump_pipeline_executables(device, pipeline, executable_dir);
    if (binary_dir)
        dump_pipeline_binary(device, pipeline, binary_dir);

    VkCommandPoolCreateInfo cp_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .queueFamilyIndex = qf,
    };
    VkCommandPool pool;
    CHECK(vkCreateCommandPool(device, &cp_info, NULL, &pool));
    VkCommandBufferAllocateInfo cb_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool,
        .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1,
    };
    VkCommandBuffer cmd;
    CHECK(vkAllocateCommandBuffers(device, &cb_info, &cmd));
    VkImage resource_image = VK_NULL_HANDLE;
    VkDeviceMemory resource_memory = VK_NULL_HANDLE;
    VkImageView resource_view = VK_NULL_HANDLE;
    VkSampler resource_sampler = VK_NULL_HANDLE;
    VkBuffer resource_staging_buffer = VK_NULL_HANDLE;
    VkDeviceMemory resource_staging_memory = VK_NULL_HANDLE;
    VkDescriptorPool fragment_descriptor_pool = VK_NULL_HANDLE;
    VkDescriptorSet fragment_descriptor_set = VK_NULL_HANDLE;
    if (fragment_texture || fragment_image || fragment_bindless ||
        fragment_footprint) {
        VkImageCreateInfo image_info = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
            .imageType = VK_IMAGE_TYPE_2D,
            .format = VK_FORMAT_R8G8B8A8_UNORM,
            .extent = {64, 64, 1},
            .mipLevels = 1,
            .arrayLayers = 1,
            .samples = VK_SAMPLE_COUNT_1_BIT,
            .tiling = VK_IMAGE_TILING_OPTIMAL,
            .usage = VK_IMAGE_USAGE_SAMPLED_BIT |
                     VK_IMAGE_USAGE_STORAGE_BIT |
                     VK_IMAGE_USAGE_TRANSFER_DST_BIT,
            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        };
        CHECK(vkCreateImage(device, &image_info, NULL, &resource_image));
        VkMemoryRequirements req;
        vkGetImageMemoryRequirements(device, resource_image, &req);
        VkMemoryAllocateInfo alloc_info = {
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .allocationSize = req.size,
            .memoryTypeIndex = find_memory_type(
                physical, req.memoryTypeBits,
                VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT),
        };
        CHECK(vkAllocateMemory(device, &alloc_info, NULL, &resource_memory));
        CHECK(vkBindImageMemory(
            device, resource_image, resource_memory, 0));
        VkImageViewCreateInfo view_info = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
            .image = resource_image,
            .viewType = VK_IMAGE_VIEW_TYPE_2D,
            .format = VK_FORMAT_R8G8B8A8_UNORM,
            .subresourceRange = {
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .levelCount = 1,
                .layerCount = 1,
            },
        };
        CHECK(vkCreateImageView(
            device, &view_info, NULL, &resource_view));
        if (fragment_texture || fragment_bindless || fragment_footprint) {
            VkSamplerCreateInfo sampler_info = {
                .sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO,
                .magFilter = VK_FILTER_NEAREST,
                .minFilter = VK_FILTER_NEAREST,
                .mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST,
                .addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                .addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                .addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                .maxLod = 0.0f,
            };
            CHECK(vkCreateSampler(
                device, &sampler_info, NULL, &resource_sampler));
        }

        const VkDeviceSize staging_size = 64u * 64u * 4u;
        VkBufferCreateInfo buffer_info = {
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .size = staging_size,
            .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
        };
        CHECK(vkCreateBuffer(
            device, &buffer_info, NULL, &resource_staging_buffer));
        vkGetBufferMemoryRequirements(
            device, resource_staging_buffer, &req);
        alloc_info = (VkMemoryAllocateInfo) {
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .allocationSize = req.size,
            .memoryTypeIndex = find_memory_type(
                physical, req.memoryTypeBits,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                    VK_MEMORY_PROPERTY_HOST_COHERENT_BIT),
        };
        CHECK(vkAllocateMemory(
            device, &alloc_info, NULL, &resource_staging_memory));
        CHECK(vkBindBufferMemory(
            device, resource_staging_buffer, resource_staging_memory, 0));
        void *mapped = NULL;
        CHECK(vkMapMemory(
            device, resource_staging_memory, 0, staging_size, 0, &mapped));
        uint8_t *pixels = mapped;
        for (uint32_t y = 0; y < 64; ++y) {
            for (uint32_t x = 0; x < 64; ++x) {
                uint8_t *pixel = &pixels[(y * 64u + x) * 4u];
                pixel[0] = (uint8_t)(x * 4u);
                pixel[1] = (uint8_t)(y * 4u);
                pixel[2] = (uint8_t)((x + y) * 2u);
                pixel[3] = 255;
            }
        }
        vkUnmapMemory(device, resource_staging_memory);

        VkDescriptorPoolSize pool_sizes[2];
        uint32_t pool_size_count = 0;
        if (fragment_texture || fragment_bindless || fragment_footprint) {
            pool_sizes[pool_size_count++] = (VkDescriptorPoolSize) {
                .type = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
                .descriptorCount = fragment_bindless ? 8u : 1u,
            };
        }
        if (fragment_image) {
            pool_sizes[pool_size_count++] = (VkDescriptorPoolSize) {
                .type = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,
                .descriptorCount = fragment_image_bindless ? 8u : 1u,
            };
        }
        VkDescriptorPoolCreateInfo pool_info = {
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
            .maxSets = 1,
            .poolSizeCount = pool_size_count,
            .pPoolSizes = pool_sizes,
        };
        CHECK(vkCreateDescriptorPool(
            device, &pool_info, NULL, &fragment_descriptor_pool));
        VkDescriptorSetAllocateInfo set_info = {
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
            .descriptorPool = fragment_descriptor_pool,
            .descriptorSetCount = 1,
            .pSetLayouts = &descriptor_layout,
        };
        CHECK(vkAllocateDescriptorSets(
            device, &set_info, &fragment_descriptor_set));
        VkDescriptorImageInfo image_descriptors[8] = {0};
        for (uint32_t i = 0; i < 8; ++i) {
            image_descriptors[i].imageView = resource_view;
            image_descriptors[i].imageLayout = VK_IMAGE_LAYOUT_GENERAL;
        }
        VkDescriptorImageInfo image_descriptor = {
            .imageView = resource_view,
            .imageLayout = VK_IMAGE_LAYOUT_GENERAL,
        };
        VkWriteDescriptorSet writes[2];
        uint32_t write_count = 0;
        if (fragment_texture || fragment_bindless || fragment_footprint) {
            image_descriptor.sampler = resource_sampler;
            for (uint32_t i = 0; i < 8; ++i)
                image_descriptors[i].sampler = resource_sampler;
            writes[write_count++] = (VkWriteDescriptorSet) {
                .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
                .dstSet = fragment_descriptor_set,
                .dstBinding = 0,
                .descriptorCount = fragment_bindless ? 8u : 1u,
                .descriptorType =
                    VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
                .pImageInfo = fragment_bindless
                                  ? image_descriptors
                                  : &image_descriptor,
            };
        }
        if (fragment_image) {
            image_descriptor.sampler = VK_NULL_HANDLE;
            writes[write_count++] = (VkWriteDescriptorSet) {
                .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
                .dstSet = fragment_descriptor_set,
                .dstBinding = 1,
                .descriptorCount = fragment_image_bindless ? 8u : 1u,
                .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,
                .pImageInfo = fragment_image_bindless
                                  ? image_descriptors
                                  : &image_descriptor,
            };
        }
        vkUpdateDescriptorSets(device, write_count, writes, 0, NULL);
    }
    if (fragment_subpass) {
        VkDescriptorPoolSize pool_size = {
            .type = VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT,
            .descriptorCount = 1,
        };
        VkDescriptorPoolCreateInfo pool_info = {
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
            .maxSets = 1,
            .poolSizeCount = 1,
            .pPoolSizes = &pool_size,
        };
        CHECK(vkCreateDescriptorPool(
            device, &pool_info, NULL, &fragment_descriptor_pool));
        VkDescriptorSetAllocateInfo set_info = {
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
            .descriptorPool = fragment_descriptor_pool,
            .descriptorSetCount = 1,
            .pSetLayouts = &descriptor_layout,
        };
        CHECK(vkAllocateDescriptorSets(
            device, &set_info, &fragment_descriptor_set));
        VkDescriptorImageInfo image_info = {
            .imageView = views[0],
            .imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
        };
        VkWriteDescriptorSet write = {
            .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
            .dstSet = fragment_descriptor_set,
            .dstBinding = 2,
            .descriptorCount = 1,
            .descriptorType = VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT,
            .pImageInfo = &image_info,
        };
        vkUpdateDescriptorSets(device, 1, &write, 0, NULL);
    }
    VkBuffer input_buffer = VK_NULL_HANDLE;
    VkDeviceMemory input_memory = VK_NULL_HANDLE;
    if (vertex_input) {
        const float input_vertices[] = {
            -1.0f, -1.0f, 0.0f, 1.0f,  1.0f, 0.0f, 0.0f, 1.0f,
             3.0f, -1.0f, 0.0f, 1.0f,  0.0f, 1.0f, 0.0f, 1.0f,
            -1.0f,  3.0f, 0.0f, 1.0f,  0.0f, 0.0f, 1.0f, 1.0f,
        };
        VkBufferCreateInfo buffer_info = {
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .size = sizeof(input_vertices),
            .usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
        };
        CHECK(vkCreateBuffer(device, &buffer_info, NULL, &input_buffer));
        VkMemoryRequirements req;
        vkGetBufferMemoryRequirements(device, input_buffer, &req);
        VkMemoryAllocateInfo alloc_info = {
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .allocationSize = req.size,
            .memoryTypeIndex = find_memory_type(
                physical, req.memoryTypeBits,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                    VK_MEMORY_PROPERTY_HOST_COHERENT_BIT),
        };
        CHECK(vkAllocateMemory(device, &alloc_info, NULL, &input_memory));
        CHECK(vkBindBufferMemory(device, input_buffer, input_memory, 0));
        void *mapped = NULL;
        CHECK(vkMapMemory(device, input_memory, 0, sizeof(input_vertices), 0,
                          &mapped));
        memcpy(mapped, input_vertices, sizeof(input_vertices));
        vkUnmapMemory(device, input_memory);
    }
    VkBuffer ssbo_buffer = VK_NULL_HANDLE;
    VkDeviceMemory ssbo_memory = VK_NULL_HANDLE;
    VkDescriptorPool descriptor_pool = VK_NULL_HANDLE;
    VkDescriptorSet descriptor_set = VK_NULL_HANDLE;
    if (vertex_ssbo) {
        const float ssbo_values[32u * 4u] = {
            -1.0f, -1.0f, 0.0f, 1.0f,
             3.0f, -1.0f, 0.0f, 1.0f,
            -1.0f,  3.0f, 0.0f, 1.0f,
             0.0f,  0.0f, 0.0f, 0.0f,
             0.0f,  0.0f, 0.0f, 0.0f,
             0.0f,  0.0f, 0.0f, 0.0f,
        };
        VkBufferCreateInfo buffer_info = {
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .size = sizeof(ssbo_values),
            .usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
        };
        CHECK(vkCreateBuffer(device, &buffer_info, NULL, &ssbo_buffer));
        VkMemoryRequirements req;
        vkGetBufferMemoryRequirements(device, ssbo_buffer, &req);
        VkMemoryAllocateInfo alloc_info = {
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .allocationSize = req.size,
            .memoryTypeIndex = find_memory_type(
                physical, req.memoryTypeBits,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                    VK_MEMORY_PROPERTY_HOST_COHERENT_BIT),
        };
        CHECK(vkAllocateMemory(device, &alloc_info, NULL, &ssbo_memory));
        CHECK(vkBindBufferMemory(device, ssbo_buffer, ssbo_memory, 0));
        void *mapped = NULL;
        CHECK(vkMapMemory(device, ssbo_memory, 0, sizeof(ssbo_values), 0,
                          &mapped));
        memcpy(mapped, ssbo_values, sizeof(ssbo_values));
        vkUnmapMemory(device, ssbo_memory);

        VkDescriptorPoolSize pool_size = {
            .type = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
            .descriptorCount = 1,
        };
        VkDescriptorPoolCreateInfo pool_info = {
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
            .maxSets = 1,
            .poolSizeCount = 1,
            .pPoolSizes = &pool_size,
        };
        CHECK(vkCreateDescriptorPool(
            device, &pool_info, NULL, &descriptor_pool));
        VkDescriptorSetAllocateInfo set_info = {
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
            .descriptorPool = descriptor_pool,
            .descriptorSetCount = 1,
            .pSetLayouts = &descriptor_layout,
        };
        CHECK(vkAllocateDescriptorSets(device, &set_info, &descriptor_set));
        VkDescriptorBufferInfo buffer_descriptor = {
            .buffer = ssbo_buffer,
            .offset = 0,
            .range = VK_WHOLE_SIZE,
        };
        VkWriteDescriptorSet write = {
            .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
            .dstSet = descriptor_set,
            .dstBinding = 0,
            .descriptorCount = 1,
            .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
            .pBufferInfo = &buffer_descriptor,
        };
        vkUpdateDescriptorSets(device, 1, &write, 0, NULL);
    }
    VkBuffer readback_buffer = VK_NULL_HANDLE;
    VkDeviceMemory readback_memory = VK_NULL_HANDLE;
    void *readback_mapped = NULL;
    VkDeviceSize target_readback_offsets[MAX_COLOR_TARGETS] = {0};
    VkDeviceSize readback_size = 0;
    for (uint32_t i = 0; i < color_targets; ++i) {
        target_readback_offsets[i] = readback_size;
        readback_size +=
            64u * 64u * format_texel_size(color_formats[i]);
    }
    VkDeviceSize depth_readback_offset = readback_size;
    if (depth_output)
        readback_size += 64u * 64u * sizeof(float);
    if (readback) {
        VkBufferCreateInfo buffer_info = {
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .size = readback_size,
            .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
        };
        CHECK(vkCreateBuffer(device, &buffer_info, NULL, &readback_buffer));
        VkMemoryRequirements req;
        vkGetBufferMemoryRequirements(device, readback_buffer, &req);
        VkMemoryAllocateInfo alloc_info = {
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .allocationSize = req.size,
            .memoryTypeIndex = find_memory_type(
                physical, req.memoryTypeBits,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                    VK_MEMORY_PROPERTY_HOST_COHERENT_BIT),
        };
        CHECK(vkAllocateMemory(device, &alloc_info, NULL, &readback_memory));
        CHECK(vkBindBufferMemory(device, readback_buffer, readback_memory, 0));
    }
    VkCommandBufferBeginInfo begin = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
    };
    CHECK(vkBeginCommandBuffer(cmd, &begin));
    if (resource_image) {
        VkImageMemoryBarrier barrier = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
            .srcAccessMask = 0,
            .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
            .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
            .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = resource_image,
            .subresourceRange = {
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .levelCount = 1,
                .layerCount = 1,
            },
        };
        vkCmdPipelineBarrier(
            cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL,
            1, &barrier);
        VkBufferImageCopy copy = {
            .imageSubresource = {
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .layerCount = 1,
            },
            .imageExtent = {64, 64, 1},
        };
        vkCmdCopyBufferToImage(
            cmd, resource_staging_buffer, resource_image,
            VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
        barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        barrier.dstAccessMask =
            VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT;
        barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        barrier.newLayout = VK_IMAGE_LAYOUT_GENERAL;
        vkCmdPipelineBarrier(
            cmd, VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT, 0,
            0, NULL, 0, NULL, 1, &barrier);
    }
    VkClearValue clear_values[MAX_COLOR_TARGETS + 1] = {0};
    float clear_r = 0.0f, clear_g = 0.0f, clear_b = 0.0f, clear_a = 1.0f;
    const char *clear_env = getenv("PROBE_CLEAR");
    if (clear_env)
        sscanf(clear_env, "%f,%f,%f,%f",
               &clear_r, &clear_g, &clear_b, &clear_a);
    for (uint32_t i = 0; i < color_targets; ++i) {
        if (uint_color) {
            clear_values[i].color = (VkClearColorValue){{0, 0, 0, 1}};
        } else {
            clear_values[i].color.float32[0] = clear_r;
            clear_values[i].color.float32[1] = clear_g;
            clear_values[i].color.float32[2] = clear_b;
            clear_values[i].color.float32[3] = clear_a;
        }
    }
    if (depth_output) {
        float clear_depth = 0.5f;
        const char *depth_clear_env = getenv("PROBE_DEPTH_CLEAR");
        if (depth_clear_env)
            clear_depth = strtof(depth_clear_env, NULL);
        clear_values[color_targets].depthStencil.depth = clear_depth;
    }
    VkRenderPassBeginInfo rp_begin = {
        .sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,
        .renderPass = renderpass,
        .framebuffer = framebuffer,
        .renderArea = {{0, 0}, {64, 64}},
        .clearValueCount = color_targets + (depth_output ? 1u : 0u),
        .pClearValues = clear_values,
    };
    vkCmdBeginRenderPass(cmd, &rp_begin, VK_SUBPASS_CONTENTS_INLINE);
    if (fragment_subpass)
        vkCmdNextSubpass(cmd, VK_SUBPASS_CONTENTS_INLINE);
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
    if (vertex_input) {
        VkDeviceSize offset = 0;
        vkCmdBindVertexBuffers(cmd, 0, 1, &input_buffer, &offset);
    }
    if (vertex_ssbo) {
        vkCmdBindDescriptorSets(
            cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, layout,
            0, 1, &descriptor_set, 0, NULL);
    }
    if (fragment_texture || fragment_image || fragment_subpass ||
        fragment_bindless || fragment_footprint) {
        vkCmdBindDescriptorSets(
            cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, layout,
            0, 1, &fragment_descriptor_set, 0, NULL);
    }
    if (mesh_shader) {
        PFN_vkCmdDrawMeshTasksEXT draw_mesh =
            (PFN_vkCmdDrawMeshTasksEXT)vkGetDeviceProcAddr(
                device, "vkCmdDrawMeshTasksEXT");
        if (!draw_mesh) {
            fprintf(stderr, "vkCmdDrawMeshTasksEXT unavailable\n");
            exit(1);
        }
        draw_mesh(cmd, 1, 1, 1);
    } else {
        vkCmdDraw(cmd, 3, 1, 0, 0);
    }
    vkCmdEndRenderPass(cmd);
    if (readback) {
        VkImageMemoryBarrier barriers[MAX_COLOR_TARGETS] = {0};
        for (uint32_t i = 0; i < color_targets; ++i) {
            barriers[i] = (VkImageMemoryBarrier) {
            .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
            .srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
            .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT,
            .oldLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
            .newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = images[i],
            .subresourceRange = {
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .levelCount = 1,
                .layerCount = 1,
            },
            };
        }
        vkCmdPipelineBarrier(
            cmd, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL,
            color_targets, barriers);
        for (uint32_t i = 0; i < color_targets; ++i) {
            VkBufferImageCopy copy = {
                .bufferOffset = target_readback_offsets[i],
                .imageSubresource = {
                    .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                    .layerCount = 1,
                },
                .imageExtent = {64, 64, 1},
            };
            vkCmdCopyImageToBuffer(cmd, images[i],
                                   VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                                   readback_buffer, 1, &copy);
        }
        if (depth_output) {
            VkImageMemoryBarrier depth_barrier = {
                .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
                .srcAccessMask =
                    VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT,
                .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT,
                .oldLayout =
                    VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL,
                .newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .image = depth_image,
                .subresourceRange = {
                    .aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT,
                    .levelCount = 1,
                    .layerCount = 1,
                },
            };
            vkCmdPipelineBarrier(
                cmd, VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT,
                VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL,
                1, &depth_barrier);
            VkBufferImageCopy depth_copy = {
                .bufferOffset = depth_readback_offset,
                .imageSubresource = {
                    .aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT,
                    .layerCount = 1,
                },
                .imageExtent = {64, 64, 1},
            };
            vkCmdCopyImageToBuffer(
                cmd, depth_image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                readback_buffer, 1, &depth_copy);
        }
    }
    CHECK(vkEndCommandBuffer(cmd));
    VkSubmitInfo submit = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1,
        .pCommandBuffers = &cmd,
    };
    CHECK(vkQueueSubmit(queue, 1, &submit, VK_NULL_HANDLE));
    CHECK(vkQueueWaitIdle(queue));
    const char *hold_ms_env = getenv("PROBE_HOLD_AFTER_DRAW_MS");
    if (hold_ms_env) {
        fflush(stdout);
        usleep((useconds_t)strtoul(hold_ms_env, NULL, 0) * 1000u);
    }
    if (vertex_ssbo) {
        void *mapped = NULL;
        CHECK(vkMapMemory(device, ssbo_memory, 0, VK_WHOLE_SIZE, 0, &mapped));
        const float *values = mapped;
        for (uint32_t i = 0; i < 6; ++i) {
            printf("ssbo[%u] = %g %g %g %g\n", i,
                   values[i * 4u + 0], values[i * 4u + 1],
                   values[i * 4u + 2], values[i * 4u + 3]);
        }
        vkUnmapMemory(device, ssbo_memory);
    }
    if (readback) {
        CHECK(vkMapMemory(device, readback_memory, 0, readback_size, 0,
                          &readback_mapped));
        uint32_t grid_width = 4;
        uint32_t grid_height = 4;
        const char *grid_size = getenv("PROBE_READBACK_GRID_SIZE");
        if (grid_size)
            sscanf(grid_size, "%ux%u", &grid_width, &grid_height);
        for (uint32_t target = 0; target < color_targets; ++target) {
            const uint8_t *target_data =
                (const uint8_t *)readback_mapped +
                target_readback_offsets[target];
            if (uint_color || mixed_outputs) {
                const uint32_t *v = (const uint32_t *)target_data;
                printf("rt%u.pixel0.u32 =", target);
                for (uint32_t c = 0; c < color_components[target]; ++c)
                    printf(" %08x", v[c]);
                printf("\n");
                uint32_t nonzero = 0;
                uint32_t shown = 0;
                for (uint32_t px = 0; px < 64u * 64u; ++px) {
                    const uint32_t *p =
                        &v[px * color_components[target]];
                    if (p[0] == 0 &&
                        (color_components[target] < 2 || p[1] == 0))
                        continue;
                    ++nonzero;
                    if (shown < 16) {
                        printf("rt%u.nonzero[%u] =", target, px);
                        for (uint32_t c = 0;
                             c < color_components[target]; ++c)
                            printf(" %08x", p[c]);
                        printf("\n");
                        ++shown;
                    }
                }
                printf("rt%u nonzero R0/R1 pixels = %u / %u\n",
                       target, nonzero, 64u * 64u);
                if (getenv("PROBE_READBACK_GRID")) {
                    for (uint32_t y = 0; y < grid_height; ++y) {
                        printf("rt%u.row%u =", target, y);
                        for (uint32_t x = 0; x < grid_width; ++x) {
                            const uint32_t *pixel =
                                &v[(y * 64u + x) *
                                   color_components[target]];
                            printf(" (");
                            for (uint32_t c = 0;
                                 c < color_components[target]; ++c)
                                printf("%s%08x", c ? "," : "", pixel[c]);
                            printf(")");
                        }
                        printf("\n");
                    }
                }
            } else {
                const uint8_t *v = target_data;
                printf("rt%u.pixel0.unorm = %u %u %u %u\n",
                       target, v[0], v[1], v[2], v[3]);
                if (getenv("PROBE_READBACK_GRID")) {
                    for (uint32_t y = 0; y < grid_height; ++y) {
                        printf("rt%u.row%u =", target, y);
                        for (uint32_t x = 0; x < grid_width; ++x) {
                            const uint8_t *pixel =
                                &v[(y * 64u + x) * 4u];
                            printf(" (%u,%u,%u,%u)",
                                   pixel[0], pixel[1],
                                   pixel[2], pixel[3]);
                        }
                        printf("\n");
                    }
                }
            }
        }
        if (depth_output) {
            const float *depth_values =
                (const float *)((const uint8_t *)readback_mapped +
                                depth_readback_offset);
            const uint32_t *depth_bits = (const uint32_t *)depth_values;
            printf("depth.pixel0.f32 = %.9g (0x%08x)\n",
                   depth_values[0], depth_bits[0]);
        }
        vkUnmapMemory(device, readback_memory);
    }
    printf("graphics pipeline compile and draw complete\n");

    vkDestroyCommandPool(device, pool, NULL);
    vkDestroyPipeline(device, pipeline, NULL);
    vkDestroyPipelineLayout(device, layout, NULL);
    if (readback_buffer)
        vkDestroyBuffer(device, readback_buffer, NULL);
    if (readback_memory)
        vkFreeMemory(device, readback_memory, NULL);
    if (input_buffer)
        vkDestroyBuffer(device, input_buffer, NULL);
    if (input_memory)
        vkFreeMemory(device, input_memory, NULL);
    if (descriptor_pool)
        vkDestroyDescriptorPool(device, descriptor_pool, NULL);
    if (fragment_descriptor_pool)
        vkDestroyDescriptorPool(device, fragment_descriptor_pool, NULL);
    if (ssbo_buffer)
        vkDestroyBuffer(device, ssbo_buffer, NULL);
    if (ssbo_memory)
        vkFreeMemory(device, ssbo_memory, NULL);
    if (resource_sampler)
        vkDestroySampler(device, resource_sampler, NULL);
    if (resource_view)
        vkDestroyImageView(device, resource_view, NULL);
    if (resource_staging_buffer)
        vkDestroyBuffer(device, resource_staging_buffer, NULL);
    if (resource_staging_memory)
        vkFreeMemory(device, resource_staging_memory, NULL);
    if (resource_image)
        vkDestroyImage(device, resource_image, NULL);
    if (resource_memory)
        vkFreeMemory(device, resource_memory, NULL);
    if (descriptor_layout)
        vkDestroyDescriptorSetLayout(device, descriptor_layout, NULL);
    if (geom)
        vkDestroyShaderModule(device, geom, NULL);
    if (tesc)
        vkDestroyShaderModule(device, tesc, NULL);
    if (tese)
        vkDestroyShaderModule(device, tese, NULL);
    if (mesh)
        vkDestroyShaderModule(device, mesh, NULL);
    if (frag)
        vkDestroyShaderModule(device, frag, NULL);
    vkDestroyShaderModule(device, vert, NULL);
    vkDestroyFramebuffer(device, framebuffer, NULL);
    vkDestroyRenderPass(device, renderpass, NULL);
    for (uint32_t i = 0; i < color_targets; ++i) {
        vkDestroyImageView(device, views[i], NULL);
        vkDestroyImage(device, images[i], NULL);
        vkFreeMemory(device, image_memories[i], NULL);
    }
    if (depth_view)
        vkDestroyImageView(device, depth_view, NULL);
    if (depth_image)
        vkDestroyImage(device, depth_image, NULL);
    if (depth_image_memory)
        vkFreeMemory(device, depth_image_memory, NULL);
    vkDestroyDevice(device, NULL);
    vkDestroyInstance(instance, NULL);
    free(devices);
    return 0;
}
