/* Actual NoMount/SUSFS callback bodies with explicit VFS/LSM/rule models. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "stat_payload.h"

#define KERNEL_VERSION(a,b,c) (((a)<<16)+((b)<<8)+(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(4,19,325)
#define IDMAP_ARG
#define IDMAP_CALL
#define likely(x) (x)
#define unlikely(x) (x)
#define KSTAT_QUERY_FLAGS 0x6000
struct path;
struct super_block { dev_t s_dev; };
struct inode_operations { int (*getattr)(const struct path *,struct kstat *,u32,unsigned); };
struct inode { struct inode_operations *i_op; void *i_private; u64 i_ino; struct super_block *i_sb; };
struct dentry { struct inode *inode; };
struct vfsmount { u64 id, visible; };
struct path { struct dentry *dentry; struct vfsmount *mnt; };
struct nm_inode_info { struct path r_path; };
static int lsm_error, backing_error, lsm_calls, backing_calls, spoof_calls;
static bool hidden, outer_rule, backing_rule;
static struct inode outer_inode, backing_inode;
static struct inode *d_backing_inode(struct dentry *d) { return d->inode; }
static void generic_fillattr(struct inode *i,struct kstat *s) {
    s->ino=i->i_ino; s->dev=i->i_sb->s_dev; s->size=123;
}
static int security_inode_getattr(const struct path *p) { lsm_calls++; return lsm_error; }
static bool susfs_mnt_hide_current(void) { return hidden; }
static u64 susfs_mnt_id(struct vfsmount *m) { return m->id; }
static u64 susfs_mnt_nonhidden_id(struct vfsmount *m) { return m->visible; }
/* Rule lookup/RCU ownership has its own actual-handler suite. Here we model
 * per-inode matches to check the two real nested callback implementations. */
static void susfs_spoof_kstat(struct inode *i,struct kstat *s,u64 *id) {
    spoof_calls++;
    if (i==&backing_inode && backing_rule) {
        s->ino=888; s->size=456;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
        if(id)*id=88;
#endif
    }
    if (i==&outer_inode && outer_rule) {
        s->ino=777;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
        if(id)*id=77;
#endif
    }
}
static int backing_getattr(const struct path *p,struct kstat *s,u32 mask,unsigned query) {
    backing_calls++; assert(mask==STATX_BASIC_STATS); assert(query==0);
    if(backing_error)return backing_error;
    generic_fillattr(d_backing_inode(p->dentry),s); return 0;
}
#include "susfs_getattr.h"
#include "nomount_getattr.h"

static struct super_block outer_sb={7}, backing_sb={9};
static struct dentry outer_dentry={&outer_inode},backing_dentry={&backing_inode};
static struct vfsmount outer_mount={55,11},backing_mount={66,22};
static struct path outer_path={&outer_dentry,&outer_mount};
static struct nm_inode_info info={{&backing_dentry,&backing_mount}};
static struct inode_operations outer_ops={nm_getattr},backing_ops={backing_getattr};
static void reset(void) {
    lsm_error=backing_error=lsm_calls=backing_calls=spoof_calls=0;
    hidden=outer_rule=backing_rule=false;
    outer_inode=(struct inode){&outer_ops,&info,101,&outer_sb};
    backing_inode=(struct inode){&backing_ops,NULL,202,&backing_sb};
    info.r_path=(struct path){&backing_dentry,&backing_mount};
}
static int query(struct kstat *s,u64 *id) {
    return vfs_getattr_mnt_id(&outer_path,s,STATX_BASIC_STATS,0,id);
}
int main(void) {
    struct { u64 before; struct kstat value; u64 after; } result;
    u64 id;
    for(int hide=0;hide<2;hide++)for(int backing=0;backing<2;backing++)for(int outer=0;outer<2;outer++) {
        reset();hidden=hide;backing_rule=backing;outer_rule=outer;id=0;
        result.before=0x12345678;result.after=0x87654321;
        assert(query(&result.value,&id)==0);
        assert(lsm_calls==1 && backing_calls==1);
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
        assert(result.value.ino==(outer?777:101));
        assert(result.value.size==(backing?456:123));
        assert(spoof_calls==2);
#else
        assert(result.value.ino==101 && result.value.size==123 && !spoof_calls);
#endif
        assert(result.value.dev==7);
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
        u64 expected=hide?11:55;
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
        if(outer)expected=77;
#endif
        assert(id==expected); /* Backing mount/rule never overwrites outer ID. */
#else
        assert(id==0);
#endif
        assert(result.before==0x12345678 && result.after==0x87654321);
    }
    reset();lsm_error=-EACCES;assert(query(&result.value,&id)==-EACCES && !backing_calls);
    reset();backing_error=-EIO;assert(query(&result.value,&id)==-EIO && !spoof_calls);
    reset();outer_inode.i_private=NULL;assert(query(&result.value,&id)==-EIO);
    reset();info.r_path.dentry=NULL;assert(!query(&result.value,&id) && !backing_calls && result.value.ino==101);
    puts("PASS: nested NoMount/SUSFS getattr, LSM denial, errors, rule ordering, private mount IDs and native kstat canaries");
}
