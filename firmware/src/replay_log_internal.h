#ifndef CYBERTRACK_REPLAY_LOG_INTERNAL_H
#define CYBERTRACK_REPLAY_LOG_INTERNAL_H
#include "cybertrack/replay_log.h"
/* Store-only primitives. prepare requires an already reserved unique attempt
 * epoch, and receives the exact NEXT anchor record, not the current one. */
bool ct_replay_log_prepare(ct_replay_log *log, ct_replay_anchor_record next,
                           const unsigned char *filter);
bool ct_replay_log_read(ct_replay_log *log, ct_replay_anchor_record selected,
                        unsigned char *filter);
#endif
