#ifndef CYBERTRACK_REPLAY_LOG_INTERNAL_H
#define CYBERTRACK_REPLAY_LOG_INTERNAL_H
#include "cybertrack/replay_log.h"
/* Store-only primitives. Preserve evidence matching current while preparing
 * next. Epoch-only bridges carry the unchanged current history; new-content
 * candidates require a previously allocated unique attempt epoch. Equal
 * current/next seeds or verifies exact history. Redundant mode preserves the
 * current pair while writing BOTH next replicas, and repairs missing seed
 * replicas without overwriting surviving exact evidence. */
bool ct_replay_log_prepare(ct_replay_log *log, ct_replay_anchor_record current,
                           ct_replay_anchor_record next, const unsigned char *filter);
bool ct_replay_log_read(ct_replay_log *log, ct_replay_anchor_record selected,
                        unsigned char *filter);
#endif
