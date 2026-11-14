#include <vulkan/vulkan.h>
#include <cuda_runtime.h>

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define VK_CHECK(call) \
    do { \
        VkResult result_ = (call); \
        if (result_ != VK_SUCCESS) { \
            fprintf(stderr, "%s failed: %d\n", #call, result_); \
            exit(1); \
        } \
    } while (0)

#define CU_CHECK(call) \
    do { \
        cudaError_t result_ = (call); \
        if (result_ != cudaSuccess) { \
            fprintf(stderr, "%s failed: %s\n", #call, \
                    cudaGetErrorString(result_)); \
            exit(1); \
        } \
    } while (0)

enum {
    WIDTH = 64,
    HEIGHT = 64,
};

static uint32_t find_memory_type(
    VkPhysicalDevice physical, uint32_t type_bits,
    VkMemoryPropertyFlags properties)
{
    VkPhysicalDeviceMemoryProperties memory;
    vkGetPhysicalDeviceMemoryProperties(physical, &memory);
    for (uint32_t i = 0; i < memory.memoryTypeCount; ++i) {
        if ((type_bits & (1u << i)) &&
            (memory.memoryTypes[i].propertyFlags & properties) == properties)
            return i;
    }
    fprintf(stderr, "no suitable Vulkan memory type\n");
    exit(1);
}

static void print_image_external_properties(
    VkPhysicalDevice physical, VkFormat format)
{
    VkPhysicalDeviceExternalImageFormatInfo external = {
        .sType =
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_IMAGE_FORMAT_INFO,
        .handleType =
            VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT,
    };
    VkExternalImageFormatProperties external_properties = {
        .sType =
            VK_STRUCTURE_TYPE_EXTERNAL_IMAGE_FORMAT_PROPERTIES,
    };
    VkImageFormatProperties2 properties = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_FORMAT_PROPERTIES_2,
        .pNext = &external_properties,
    };
    VkResult result = vkGetPhysicalDeviceImageFormatProperties2(
        physical, &(VkPhysicalDeviceImageFormatInfo2) {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_FORMAT_INFO_2,
            .pNext = &external,
            .format = format,
            .type = VK_IMAGE_TYPE_2D,
            .tiling = VK_IMAGE_TILING_OPTIMAL,
            .usage = VK_IMAGE_USAGE_STORAGE_BIT |
                     VK_IMAGE_USAGE_TRANSFER_DST_BIT,
        }, &properties);
    printf(
        "external image query: result=%d features=0x%x handleTypes=0x%x\n",
        result, external_properties.externalMemoryProperties.externalMemoryFeatures,
        external_properties.externalMemoryProperties.compatibleHandleTypes);
}

static int cuda_device_for_name(const char *wanted)
{
    int count = 0;
    CU_CHECK(cudaGetDeviceCount(&count));
    for (int i = 0; i < count; ++i) {
        struct cudaDeviceProp properties;
        CU_CHECK(cudaGetDeviceProperties(&properties, i));
        if (strstr(properties.name, wanted))
            return i;
    }
    fprintf(stderr, "no CUDA device matching '%s'\n", wanted);
    exit(1);
}

static VkDeviceSize rgba8_optimal_offset(uint32_t x, uint32_t y)
{
    uint32_t word =
        (x & 3) |
        ((y & 3) << 2) |
        (((x >> 2) & 1) << 4) |
        (((y >> 2) & 1) << 5) |
        (((x >> 3) & 1) << 6) |
        (((y >> 3) & 1) << 7) |
        (((y >> 4) & 1) << 8) |
        (((y >> 5) & 1) << 9) |
        (((x >> 4) & 1) << 10) |
        (((x >> 5) & 1) << 11);
    return (VkDeviceSize)word * 4;
}

int main(void)
{
    const char *wanted_gpu =
        getenv("PROBE_GPU_NAME") ? getenv("PROBE_GPU_NAME") : "TITAN RTX";
    const VkFormat format = VK_FORMAT_R8G8B8A8_UNORM;

    VkApplicationInfo application = {
        .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "vulkan-cuda-interop-probe",
        .apiVersion = VK_API_VERSION_1_4,
    };
    VkInstanceCreateInfo instance_info = {
        .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &application,
    };
    VkInstance instance;
    VK_CHECK(vkCreateInstance(&instance_info, NULL, &instance));

    uint32_t physical_count = 0;
    VK_CHECK(vkEnumeratePhysicalDevices(
        instance, &physical_count, NULL));
    VkPhysicalDevice *physical_devices =
        calloc(physical_count, sizeof(*physical_devices));
    VK_CHECK(vkEnumeratePhysicalDevices(
        instance, &physical_count, physical_devices));

    VkPhysicalDevice physical = VK_NULL_HANDLE;
    uint32_t queue_family = UINT32_MAX;
    for (uint32_t i = 0; i < physical_count; ++i) {
        VkPhysicalDeviceProperties properties;
        vkGetPhysicalDeviceProperties(physical_devices[i], &properties);
        if (strstr(properties.deviceName, wanted_gpu)) {
            uint32_t queue_count = 0;
            vkGetPhysicalDeviceQueueFamilyProperties(
                physical_devices[i], &queue_count, NULL);
            VkQueueFamilyProperties *queues =
                calloc(queue_count, sizeof(*queues));
            vkGetPhysicalDeviceQueueFamilyProperties(
                physical_devices[i], &queue_count, queues);
            for (uint32_t q = 0; q < queue_count; ++q) {
                if (queues[q].queueFlags & VK_QUEUE_GRAPHICS_BIT) {
                    queue_family = q;
                    break;
                }
            }
            free(queues);
            if (queue_family != UINT32_MAX) {
                physical = physical_devices[i];
                printf("Vulkan GPU: %s\n", properties.deviceName);
                break;
            }
        }
    }
    if (physical == VK_NULL_HANDLE) {
        fprintf(stderr, "no matching Vulkan GPU\n");
        return 1;
    }

    uint32_t extension_count = 0;
    VK_CHECK(vkEnumerateDeviceExtensionProperties(
        physical, NULL, &extension_count, NULL));
    VkExtensionProperties *extensions =
        calloc(extension_count, sizeof(*extensions));
    VK_CHECK(vkEnumerateDeviceExtensionProperties(
        physical, NULL, &extension_count, extensions));
    int has_external_fd = 0;
    for (uint32_t i = 0; i < extension_count; ++i) {
        if (!strcmp(extensions[i].extensionName,
                    VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME))
            has_external_fd = 1;
    }
    free(extensions);
    if (!has_external_fd) {
        fprintf(stderr, "VK_KHR_external_memory_fd unavailable\n");
        return 1;
    }

    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = queue_family,
        .queueCount = 1,
        .pQueuePriorities = &priority,
    };
    const char *enabled_extensions[] = {
        VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME,
    };
    VkDeviceCreateInfo device_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1,
        .pQueueCreateInfos = &queue_info,
        .enabledExtensionCount = 1,
        .ppEnabledExtensionNames = enabled_extensions,
    };
    VkDevice device;
    VK_CHECK(vkCreateDevice(physical, &device_info, NULL, &device));
    VkQueue queue;
    vkGetDeviceQueue(device, queue_family, 0, &queue);

    print_image_external_properties(physical, format);

    VkExternalMemoryImageCreateInfo external_image = {
        .sType = VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO,
        .handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT,
    };
    VkImageCreateInfo image_info = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
        .pNext = &external_image,
        .imageType = VK_IMAGE_TYPE_2D,
        .format = format,
        .extent = {WIDTH, HEIGHT, 1},
        .mipLevels = 1,
        .arrayLayers = 1,
        .samples = VK_SAMPLE_COUNT_1_BIT,
        .tiling = VK_IMAGE_TILING_OPTIMAL,
        .usage = VK_IMAGE_USAGE_STORAGE_BIT |
                 VK_IMAGE_USAGE_TRANSFER_DST_BIT,
        .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
    };
    VkImage image;
    VK_CHECK(vkCreateImage(device, &image_info, NULL, &image));

    VkMemoryRequirements requirements;
    vkGetImageMemoryRequirements(device, image, &requirements);
    VkMemoryDedicatedAllocateInfo dedicated = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO,
        .image = image,
    };
    VkExportMemoryAllocateInfo export_info = {
        .sType = VK_STRUCTURE_TYPE_EXPORT_MEMORY_ALLOCATE_INFO,
        .pNext = &dedicated,
        .handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT,
    };
    VkMemoryAllocateInfo memory_info = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .pNext = &export_info,
        .allocationSize = requirements.size,
        .memoryTypeIndex = find_memory_type(
            physical, requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT),
    };
    VkDeviceMemory memory;
    VK_CHECK(vkAllocateMemory(device, &memory_info, NULL, &memory));
    VK_CHECK(vkBindImageMemory(device, image, memory, 0));

    void *vulkan_mapped = NULL;
    VkResult map_result =
        vkMapMemory(device, memory, 0, VK_WHOLE_SIZE, 0, &vulkan_mapped);
    printf("vkMapMemory(device-local image allocation): result=%d ptr=%p\n",
           map_result, vulkan_mapped);
    if (map_result == VK_SUCCESS)
        vkUnmapMemory(device, memory);

    const VkDeviceSize upload_size =
        WIDTH * HEIGHT * sizeof(uint32_t);
    VkBufferCreateInfo buffer_info = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = upload_size,
        .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT |
                 VK_BUFFER_USAGE_TRANSFER_DST_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
    };
    VkBuffer upload_buffer;
    VK_CHECK(vkCreateBuffer(device, &buffer_info, NULL, &upload_buffer));
    VkMemoryRequirements buffer_requirements;
    vkGetBufferMemoryRequirements(
        device, upload_buffer, &buffer_requirements);
    VkMemoryAllocateInfo upload_alloc = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = buffer_requirements.size,
        .memoryTypeIndex = find_memory_type(
            physical, buffer_requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                VK_MEMORY_PROPERTY_HOST_COHERENT_BIT),
    };
    VkDeviceMemory upload_memory;
    VK_CHECK(vkAllocateMemory(device, &upload_alloc, NULL, &upload_memory));
    VK_CHECK(vkBindBufferMemory(
        device, upload_buffer, upload_memory, 0));

    void *upload_mapped = NULL;
    VK_CHECK(vkMapMemory(
        device, upload_memory, 0, upload_size, 0, &upload_mapped));
    uint32_t *texels = upload_mapped;
    for (uint32_t y = 0; y < HEIGHT; ++y) {
        for (uint32_t x = 0; x < WIDTH; ++x)
            texels[y * WIDTH + x] = 0xA5000000u | (y << 8) | x;
    }
    vkUnmapMemory(device, upload_memory);

    VkCommandPoolCreateInfo pool_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .queueFamilyIndex = queue_family,
    };
    VkCommandPool command_pool;
    VK_CHECK(vkCreateCommandPool(
        device, &pool_info, NULL, &command_pool));
    VkCommandBufferAllocateInfo command_alloc = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = command_pool,
        .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1,
    };
    VkCommandBuffer command;
    VK_CHECK(vkAllocateCommandBuffers(
        device, &command_alloc, &command));
    VkCommandBufferBeginInfo begin = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
    };
    VK_CHECK(vkBeginCommandBuffer(command, &begin));
    VkImageMemoryBarrier to_transfer = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
        .srcAccessMask = 0,
        .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
        .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .image = image,
        .subresourceRange = {
            .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
            .levelCount = 1,
            .layerCount = 1,
        },
    };
    vkCmdPipelineBarrier(
        command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
        VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL,
        1, &to_transfer);
    VkBufferImageCopy copy = {
        .imageSubresource = {
            .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
            .layerCount = 1,
        },
        .imageExtent = {WIDTH, HEIGHT, 1},
    };
    vkCmdCopyBufferToImage(
        command, upload_buffer, image,
        VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
    VkImageMemoryBarrier to_general = to_transfer;
    to_general.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    to_general.dstAccessMask = VK_ACCESS_SHADER_READ_BIT |
                               VK_ACCESS_SHADER_WRITE_BIT;
    to_general.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    to_general.newLayout = VK_IMAGE_LAYOUT_GENERAL;
    vkCmdPipelineBarrier(
        command, VK_PIPELINE_STAGE_TRANSFER_BIT,
        VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, NULL, 0, NULL,
        1, &to_general);
    VK_CHECK(vkEndCommandBuffer(command));
    VkSubmitInfo submit = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1,
        .pCommandBuffers = &command,
    };
    VK_CHECK(vkQueueSubmit(queue, 1, &submit, VK_NULL_HANDLE));
    VK_CHECK(vkQueueWaitIdle(queue));

    PFN_vkGetMemoryFdKHR get_memory_fd =
        (PFN_vkGetMemoryFdKHR)vkGetDeviceProcAddr(
            device, "vkGetMemoryFdKHR");
    if (!get_memory_fd) {
        fprintf(stderr, "vkGetMemoryFdKHR unavailable\n");
        return 1;
    }
    VkMemoryGetFdInfoKHR fd_info = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_GET_FD_INFO_KHR,
        .memory = memory,
        .handleType = VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT,
    };
    int fd = -1;
    VK_CHECK(get_memory_fd(device, &fd_info, &fd));
    printf("Vulkan image memory: size=%llu alignment=%llu fd=%d\n",
           (unsigned long long)requirements.size,
           (unsigned long long)requirements.alignment, fd);

    int cuda_device = cuda_device_for_name(wanted_gpu);
    CU_CHECK(cudaSetDevice(cuda_device));
    struct cudaExternalMemoryHandleDesc external_memory = {
        .type = cudaExternalMemoryHandleTypeOpaqueFd,
        .handle.fd = fd,
        .size = requirements.size,
        .flags = cudaExternalMemoryDedicated,
    };
    cudaExternalMemory_t imported;
    CU_CHECK(cudaImportExternalMemory(&imported, &external_memory));
    struct cudaExternalMemoryBufferDesc cuda_buffer = {
        .offset = 0,
        .size = requirements.size,
    };
    void *device_pointer = NULL;
    CU_CHECK(cudaExternalMemoryGetMappedBuffer(
        &device_pointer, imported, &cuda_buffer));

    struct cudaPointerAttributes attributes = {0};
    CU_CHECK(cudaPointerGetAttributes(&attributes, device_pointer));
    printf(
        "CUDA import: device=%d pointer=%p type=%d devicePointer=%p "
        "hostPointer=%p\n",
        cuda_device, device_pointer, (int)attributes.type,
        attributes.devicePointer, attributes.hostPointer);

    size_t raw_size = (size_t)requirements.size;
    uint8_t *raw = malloc(raw_size);
    int32_t *texel_offsets =
        malloc((size_t)WIDTH * HEIGHT * sizeof(*texel_offsets));
    for (uint32_t i = 0; i < WIDTH * HEIGHT; ++i)
        texel_offsets[i] = -1;
    CU_CHECK(cudaMemcpy(
        raw, device_pointer, raw_size, cudaMemcpyDeviceToHost));

    uint32_t marker_count = 0;
    uint32_t shown = 0;
    for (size_t offset = 0; offset + 4 <= raw_size; offset += 4) {
        uint32_t word;
        memcpy(&word, raw + offset, sizeof(word));
        uint32_t x = word & 0xff;
        uint32_t y = (word >> 8) & 0xff;
        if ((word >> 24) != 0xa5 || (word & 0x00ff0000u) != 0 ||
            x >= WIDTH || y >= HEIGHT)
            continue;
        texel_offsets[y * WIDTH + x] = (int32_t)offset;
        ++marker_count;
        if (shown < 16) {
            printf("raw[0x%05zx] = texel(%u,%u) word=0x%08x\n",
                   offset, x, y, word);
            ++shown;
        }
    }
    printf("decoded %u / %u texel markers in CUDA-visible memory\n",
           marker_count, WIDTH * HEIGHT);
    printf("row y=0:");
    for (uint32_t x = 0; x < WIDTH; ++x)
        printf(" %x", texel_offsets[x]);
    printf("\n");
    printf("column x=0:");
    for (uint32_t y = 0; y < HEIGHT; ++y)
        printf(" %x", texel_offsets[y * WIDTH]);
    printf("\n");
    printf("microtile bases (words, rows=my, cols=mx):\n");
    for (uint32_t my = 0; my < HEIGHT / 4; ++my) {
        printf("my=%02u:", my);
        for (uint32_t mx = 0; mx < WIDTH / 4; ++mx) {
            int32_t offset = texel_offsets[(my * 4) * WIDTH + mx * 4];
            printf(" %03x", offset / 4);
        }
        printf("\n");
    }
    uint32_t formula_mismatches = 0;
    for (uint32_t y = 0; y < HEIGHT; ++y) {
        for (uint32_t x = 0; x < WIDTH; ++x) {
            if ((int32_t)rgba8_optimal_offset(x, y) !=
                texel_offsets[y * WIDTH + x])
                ++formula_mismatches;
        }
    }
    printf("tiling bit-formula mismatches: %u / %u\n",
           formula_mismatches, WIDTH * HEIGHT);

    const uint32_t target_x = 5;
    const uint32_t target_y = 6;
    const uint32_t cuda_marker = 0xdeadbeefu;
    const VkDeviceSize target_offset =
        rgba8_optimal_offset(target_x, target_y);
    CU_CHECK(cudaMemcpy(
        (uint8_t *)device_pointer + target_offset,
        &cuda_marker, sizeof(cuda_marker), cudaMemcpyHostToDevice));

    VK_CHECK(vkResetCommandBuffer(command, 0));
    VK_CHECK(vkBeginCommandBuffer(command, &begin));
    VkImageMemoryBarrier to_copy_source = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
        .srcAccessMask = VK_ACCESS_SHADER_READ_BIT |
                         VK_ACCESS_SHADER_WRITE_BIT,
        .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT,
        .oldLayout = VK_IMAGE_LAYOUT_GENERAL,
        .newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .image = image,
        .subresourceRange = {
            .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
            .levelCount = 1,
            .layerCount = 1,
        },
    };
    vkCmdPipelineBarrier(
        command, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
        VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL,
        1, &to_copy_source);
    VkBufferImageCopy readback_copy = copy;
    vkCmdCopyImageToBuffer(
        command, image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
        upload_buffer, 1, &readback_copy);
    VK_CHECK(vkEndCommandBuffer(command));
    VK_CHECK(vkQueueSubmit(queue, 1, &submit, VK_NULL_HANDLE));
    VK_CHECK(vkQueueWaitIdle(queue));

    CU_CHECK(cudaDeviceSynchronize());
    VK_CHECK(vkMapMemory(
        device, upload_memory, 0, upload_size, 0, &upload_mapped));
    texels = upload_mapped;
    uint32_t vulkan_value = texels[target_y * WIDTH + target_x];
    printf("CUDA wrote 0x%08x at raw+0x%zx for texel(%u,%u); "
           "Vulkan read 0x%08x\n",
           cuda_marker, (size_t)target_offset, target_x, target_y,
           vulkan_value);
    vkUnmapMemory(device, upload_memory);

    free(texel_offsets);
    free(raw);
    cudaDestroyExternalMemory(imported);

    vkDestroyCommandPool(device, command_pool, NULL);
    vkDestroyBuffer(device, upload_buffer, NULL);
    vkFreeMemory(device, upload_memory, NULL);
    vkDestroyImage(device, image, NULL);
    vkFreeMemory(device, memory, NULL);
    vkDestroyDevice(device, NULL);
    vkDestroyInstance(instance, NULL);
    free(physical_devices);
    return marker_count == WIDTH * HEIGHT ? 0 : 2;
}
