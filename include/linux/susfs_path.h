/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_SUSFS_PATH_H
#define _LINUX_SUSFS_PATH_H

#include <linux/types.h>
#include <linux/susfs_def.h>

/* VFS consumers need path hooks, not command payloads or statfs/UTS types.
 * Avoid completing otherwise opaque public types in their export graphs.
 */
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
struct inode;
struct path;
struct qstr;
struct work_struct;
extern struct work_struct susfs_extra_works;
bool susfs_is_inode_sus_path(struct inode *inode);
int susfs_get_data_path(struct path *path);
void susfs_run_sus_path_loop(void);
extern const struct qstr susfs_fake_qstr_name;
#endif

#endif
