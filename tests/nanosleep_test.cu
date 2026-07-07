__global__ void k(int *a,int *out,unsigned ns){
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    __nanosleep(100);            // immediate
    __nanosleep(ns);             // register
    while(a[i]==0){ __nanosleep(32); }   // backoff loop
    out[i]=a[i];
}
