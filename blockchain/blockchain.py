import typing
import aiohttp
import hashlib
import json

ROOT_HASH = 30791614295234051711832508548800469788824342480481074093233550318061354680202

# For convenience in typing, we define several type aliases
type Sender = typing.Callable[[dict],typing.Awaitable[None]]

class Change(typing.TypedDict):
    old: int
    src: str
    dst: str
    n: int
    memo: str

class Block(typing.TypedDict):
    change: Change
    signature: int

class UserData(typing.TypedDict, total=False):
    key: int
    host: str


class UnsupportedOperation(Exception):
    pass


class BlockChain:
    def __init__(self):
        """Initialize a blockchain with no blocks in it."""
        self.blocks: dict[int, Block] = {}
        self.users: dict[str, UserData] = {}
        self.head: int = ROOT_HASH
        self.chain_lengths: dict[int, int] = {ROOT_HASH: 0}
        self.children: dict[int, set[int]] = {}
        self.pending: dict[int, list[Block]] = {}
        self.balances_cache: dict[int, dict[str, int]] = {}
        self.paid_cache: dict[int, dict[str, set[str]]] = {}
    
    def add_users(self, userdata: dict[str,UserData]) -> None:
        """Add users to the set known by the BlockChain.
        userdata will be a dict with the following properties:
        
        - keys are user account names
        - values are dicts which may have several keys, including
            - "key": a large int which is this agent's public key
        """
        self.users.update(userdata)
    
    def _hash_change(self, change: Change) -> int:
        string_val = json.dumps(change, separators=(',',':'), indent=None, sort_keys=True, ensure_ascii=False)
        byte_string = string_val.encode('utf-8')
        hash_bytes = hashlib.sha256(byte_string).digest()
        return int.from_bytes(hash_bytes, byteorder='big')
    
    def _verify_signature(self, block: Block) -> bool:
        change_hash = self._hash_change(block['change'])
        src = block['change']['src']
        
        if src not in self.users or 'key' not in self.users[src]:
            return False
        
        public_key = self.users[src]['key']
        signature = block['signature']
        
        return change_hash == pow(signature, 0x10001, public_key)
    
    def _is_booth(self, username: str) -> bool:
        return username.endswith('_b')
    
    def _get_player_booth_pair(self, user1: str, user2: str) -> tuple[str, str] | None:
        if self._is_booth(user1) and not self._is_booth(user2):
            return (user2, user1)
        elif self._is_booth(user2) and not self._is_booth(user1):
            return (user1, user2)
        return None
    
    def _compute_balances(self, block_hash: int) -> dict[str, int]:
        if block_hash in self.balances_cache:
            return self.balances_cache[block_hash].copy()
        
        if block_hash == ROOT_HASH:
            balances = {user: 20 for user in self.users.keys()}
            self.balances_cache[ROOT_HASH] = balances
            return balances.copy()
        
        block = self.blocks[block_hash]
        change = block['change']
        
        parent_balances = self._compute_balances(change['old'])
        
        parent_balances[change['src']] -= change['n']
        parent_balances[change['dst']] += change['n']
        
        self.balances_cache[block_hash] = parent_balances
        return parent_balances.copy()
    
    def _compute_paid_status(self, block_hash: int) -> dict[str, set[str]]:
        if block_hash in self.paid_cache:
            return {k: v.copy() for k, v in self.paid_cache[block_hash].items()}
        
        if block_hash == ROOT_HASH:
            paid = {}
            self.paid_cache[ROOT_HASH] = paid
            return {}
        
        block = self.blocks[block_hash]
        change = block['change']
        
        parent_paid = self._compute_paid_status(change['old'])
        
        pair = self._get_player_booth_pair(change['src'], change['dst'])
        if pair:
            player, booth = pair
            
            if player not in parent_paid:
                parent_paid[player] = set()
            
            if change['src'] == player:
                parent_paid[player].add(booth)
            else:
                parent_paid[player].discard(booth)
        
        self.paid_cache[block_hash] = parent_paid
        return {k: v.copy() for k, v in parent_paid.items()}
    
    def _is_valid_change(self, change: Change, check_paid: bool = True) -> str | None:
        src = change['src']
        dst = change['dst']
        n = change['n']
        
        if src not in self.users:
            return f'Unknown user: {src}'
        if dst not in self.users:
            return f'Unknown user: {dst}'
        
        pair = self._get_player_booth_pair(src, dst)
        if pair is None:
            return 'Not authorized'
        
        player, booth = pair
        
        if player + '_b' == booth:
            return 'Not authorized'
        
        if src == player:
            if n < 1 or n > 5:
                return 'Invalid amount'
        else:
            if n < 0 or n > 10:
                return 'Invalid amount'
        
        if check_paid and src == booth:
            paid_status = self._compute_paid_status(change['old'])
            if player not in paid_status or booth not in paid_status[player]:
                return 'Not paid'
        
        return None
    
    def _update_head(self, new_block_hash: int) -> None:
        new_length = self.chain_lengths[new_block_hash]
        head_length = self.chain_lengths[self.head]
        
        if new_length > head_length or (new_length == head_length and new_block_hash < self.head):
            self.head = new_block_hash

    def create_block(self, src:str, dst:str, n:int, memo:str, privkey:int) -> Block|str:
        """Create a block that would apply the given delta to the current head;
        if this cannot be done for some reason, return that reason as a string.
        Include the following strings:
        
        - 'Unknown user: «username»' if the src or dst not previously added as a user
        - 'Not authorized' if this is not a booth-to-player or player-to-booth transfer
        - 'Not authorized' if this is is a self-transfer
        - 'Invalid amount' if n is not a permitted integer
        - 'Not paid` if src is a booth and the player isn't in a paid state
        - 'Wrong key' if the privkey does not match the pubkey of the src account
        
        If multiple messages might be returned, any one of them may be returned.
        """
        change: Change = {
            'old': self.head,
            'src': src,
            'dst': dst,
            'n': n,
            'memo': memo
        }
        
        error = self._is_valid_change(change, check_paid=True)
        if error:
            return error
        
        if src not in self.users or 'key' not in self.users[src]:
            return 'Unknown user: ' + src
        
        public_key = self.users[src]['key']
        change_hash = self._hash_change(change)
        signature = pow(change_hash, privkey, public_key)
        
        if change_hash != pow(signature, 0x10001, public_key):
            return 'Wrong key'
        
        block: Block = {
            'change': change,
            'signature': signature
        }
        
        return block
        
    async def add_block(self, block: Block, send_json: Sender) -> None:
        """Add a block to the blockchain if it is valid.
        If it is invalid, ignore it.
        If it depends on a missing old value, request that through passed-in `send_json`
        and keep track of the unfinished block.
        
        If there are unfinished blocks that can be finished after adding this one,
        also add (or unverify and discard) those.
        """
        change = block['change']
        old = change['old']
        block_hash = self._hash_change(change)
        
        if block_hash in self.blocks:
            return
        
        if not self._verify_signature(block):
            return
        
        if old != ROOT_HASH and old not in self.blocks:
            if old not in self.pending:
                self.pending[old] = []
            self.pending[old].append(block)
            await send_json({'missing': old})
            return
        
        error = self._is_valid_change(change, check_paid=True)
        if error:
            return
        
        self.blocks[block_hash] = block
        
        parent_length = self.chain_lengths.get(old, 0)
        self.chain_lengths[block_hash] = parent_length + 1
        
        if old not in self.children:
            self.children[old] = set()
        self.children[old].add(block_hash)
        
        self._update_head(block_hash)
        
        if block_hash in self.pending:
            pending_blocks = self.pending[block_hash]
            del self.pending[block_hash]
            
            for pending_block in pending_blocks:
                await self.add_block(pending_block, send_json)

    def get_head_hash(self) -> int:
        """Returns the hash of the current head of the blockchain"""
        return self.head

    def get_accounts(self) -> dict[str,int]:
        """Return the ticket count of each user in the current head of the blockchain.
        If the count of a "user" is 20 (the starting amount), the function can either 
        include "user":20 or omit the "user" entry entirely (which one is implementation defined).
        """
        all_balances = self._compute_balances(self.head)
        return {k: v for k, v in all_balances.items() if v != 20}

    def get_chain(self) -> dict[int, Block]:
        """Return all the blocks that have been added to this blockchain.
        Returns a dict where keys are the hash of each block's change
        and values are block objects.
        """
        return self.blocks.copy()

    def get_block(self, blockid: int) -> Block|None:
        """Given the hash of the change of a block,
        return that block if it is present in the BlockChain.
        Should be equivalent to self.get_chain().get(blockid),
        but ideally faster and/or a smaller return value.
        """
        return self.blocks.get(blockid)

    def is_live(self, blockid: int) -> bool:
        """Given the hash of a block's change,
        return True iff the block is on the path from the head to the root.
        We recommend optimizing for the case where the chain has millions of blocks,
        the block *is* on that path, and the block is close to the head.
        """
        # The staff-provided code works, but if you can make it faster based on your datastructures and internal implementation, please do so; this method is called at least once per game played and we expect the total number of blocks to reach the hundreds of thousands
        if self.get_block(blockid) is None: return False
        ptr = self.get_head_hash()
        while ptr != ROOT_HASH:
            if ptr == blockid: return True
            ptr = self.get_block(ptr)['change']['old']
        return False