/* SPDX-License-Identifier: GPL-2.0 */
/* Fault injection around the actual imported rule function and capability gate. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define GFP_KERNEL 0
#define NM_FLAG_IS_DIR 1
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define rcu_dereference_protected(p, condition) (p)
#define RCU_INIT_POINTER(p, value) ((p) = (value))
#define rcu_assign_pointer(p, value) ((p) = (value))
#define hash_add_rcu(table, node, hash) ((void)0)
#define CAP_SYS_ADMIN 21

struct path { void *dentry; };
struct nm_rule { struct path r_path; unsigned int target_uid; u16 r_len, flags; };
struct nm_rule_array { int count; struct nm_rule rules[]; };
struct nomount_leaf;
struct nomount_dir_node { struct nomount_leaf *owner; };
struct nomount_leaf {
    struct nm_rule_array *rules;
    struct nomount_dir_node *this_dir;
    void *ht_node;
    u32 v_hash;
};
#define nm_rule_heap(arr) ((char *)((arr)->rules + (arr)->count))

static struct { int held, unlocks; } nomount_mutex;
static void mutex_unlock(void *unused)
{
    (void)unused;
    assert(nomount_mutex.held == 1);
    nomount_mutex.held = 0;
    nomount_mutex.unlocks++;
}

enum { SUCCESS, REAL_PATH_ALLOC, PREPARE_RULE, LEAF_ALLOC,
       DIRECTORY_ALLOC, ARRAY_ALLOC, TOPOLOGY };
static int fault, references;
static struct nomount_leaf existing;
static void *allocations[32];
static int allocation_count;

static void *allocate(size_t size)
{
    void *p = calloc(1, size);
    assert(p && allocation_count < 32);
    allocations[allocation_count++] = p;
    return p;
}
static void kfree(void *p)
{
    if (!p) return;
    for (int i = 0; i < allocation_count; i++) {
        if (allocations[i] == p) {
            free(p);
            allocations[i] = NULL;
            return;
        }
    }
    assert(!"untracked or double free");
}
static void *kmalloc(size_t size, int flags)
{
    (void)flags;
    return fault == REAL_PATH_ALLOC ? NULL : allocate(size);
}
static void path_get(struct path *path) { (void)path; references++; }
static void path_put(struct path *path) { (void)path; assert(references > 0); references--; }
static int nm_prepare_rule(const char *path, u16 len, u32 flags,
                           unsigned int uid, struct nm_rule *rule)
{
    (void)path;
    if (fault == PREPARE_RULE) return -ENOENT;
    *rule = (struct nm_rule){ .r_path.dentry = &existing, .r_len = len,
                              .target_uid = uid, .flags = flags };
    references++;
    return 0;
}
static struct nomount_leaf *nm_find_leaf(const char *path, u16 len)
{
    (void)path; (void)len;
    return (fault == DIRECTORY_ALLOC || fault == ARRAY_ALLOC) ? &existing : NULL;
}
static struct nomount_leaf *nm_alloc_leaf(const char *path, u16 len, u32 flags)
{
    (void)path; (void)len; (void)flags;
    return fault == LEAF_ALLOC ? ERR_PTR(-ENOMEM) : allocate(sizeof(struct nomount_leaf));
}
static struct nomount_dir_node *__nomount_alloc_dir_node(void)
{
    return fault == DIRECTORY_ALLOC ? NULL : allocate(sizeof(struct nomount_dir_node));
}
static void nm_dir_put(struct nomount_dir_node *dir) { kfree(dir); }
static struct nm_rule_array *nm_alloc_rule_array(int count, size_t heap)
{
    struct nm_rule_array *array;
    if (fault == ARRAY_ALLOC) return NULL;
    array = allocate(sizeof(*array) + count * sizeof(struct nm_rule) + heap);
    array->count = count;
    return array;
}
static void nm_free_leaf(struct nomount_leaf *leaf) { kfree(leaf); }
static int nomount_generate_virtual_topology(struct nomount_leaf *leaf, unsigned int uid)
{
    (void)leaf; (void)uid;
    return fault == TOPOLOGY ? -EIO : 0;
}
static void nm_rule_array_free(void *p) { (void)p; }
#define call_rcu(head, callback) ((void)0)

struct user_namespace { int unused; };
static struct user_namespace init_user_ns, container_user_ns;
static bool host_admin, container_admin;
static int processed;
static bool ns_capable(struct user_namespace *ns, int capability)
{
    assert(capability == CAP_SYS_ADMIN);
    assert(ns == &init_user_ns || ns == &container_user_ns);
    return ns == &init_user_ns ? host_admin : container_admin;
}
struct key_preparsed_payload { const void *data; size_t datalen; };
static int nm_process_payload(unsigned long address) { assert(address == 123); processed++; return 0; }

#include "native_nomount.h"

_Static_assert(sizeof(struct nm_payload) == 4096, "userspace page ABI");
_Static_assert(sizeof(struct nm_rule_hdr) == 12, "add record ABI");
_Static_assert(sizeof(struct nm_del_hdr) == 6, "delete record ABI");

static void test_lock_ownership(void)
{
    for (fault = SUCCESS; fault <= TOPOLOGY; fault++) {
        nomount_mutex.held = 1;
        nomount_mutex.unlocks = 0;
        references = allocation_count = 0;
        memset(&existing, 0, sizeof(existing));
        int result = __nomount_add_rule("/system/test", "/data/test", 12, 10,
                     (fault == DIRECTORY_ALLOC || fault == ARRAY_ALLOC) ? NM_FLAG_IS_DIR : 0, 100);
        assert((result == 0) == (fault == SUCCESS));
        assert(nomount_mutex.held == 1 && nomount_mutex.unlocks == 0);
        mutex_unlock(&nomount_mutex);
        assert(nomount_mutex.unlocks == 1);
        if (fault != SUCCESS) assert(references == 0);
        for (int i = 0; i < allocation_count; i++) free(allocations[i]);
    }
}

static void test_capability_scope(void)
{
    u64 address = 123;
    struct key_preparsed_payload prep = { &address, sizeof(address) };
    host_admin = container_admin = false;
    processed = 0;
    assert(nm_key_preparse(&prep) == -EPERM && processed == 0);
    container_admin = true;
    assert(nm_key_preparse(&prep) == -EPERM && processed == 0);
    host_admin = true;
    assert(nm_key_preparse(&prep) == -ECANCELED && processed == 1);
    prep.datalen = 3;
    assert(nm_key_preparse(&prep) == -EINVAL && processed == 1);
}

int main(void)
{
    test_lock_ownership();
    test_capability_scope();
    puts("PASS: native rule success/six failure paths, single unlock, host-only privilege and packet ABI");
    return 0;
}
