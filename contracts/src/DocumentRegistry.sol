// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title DocumentRegistry
/// @notice 계약 문서의 SHA-256 디지털 지문(Hash)만 기록한다.
///         이름·전화번호·주소·금액·계약 내용 등 개인정보/원문은 절대 저장하지 않는다.
contract DocumentRegistry {
    struct Record {
        uint64 timestamp;
        uint16 version;
        bool exists;
    }

    address public immutable owner;
    mapping(bytes32 => Record) private records;
    mapping(bytes32 => uint64) private roots;

    event DocumentRegistered(bytes32 indexed documentHash, uint16 version, uint64 timestamp);
    event RootRegistered(bytes32 indexed merkleRoot, uint64 timestamp);

    error NotOwner();
    error AlreadyRegistered();
    error EmptyHash();

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    /// @notice 계약 1건 = Hash 1건 기록 (MVP 기본 방식)
    function register(bytes32 documentHash, uint16 version) external onlyOwner {
        if (documentHash == bytes32(0)) revert EmptyHash();
        if (records[documentHash].exists) revert AlreadyRegistered();
        records[documentHash] = Record(uint64(block.timestamp), version, true);
        emit DocumentRegistered(documentHash, version, uint64(block.timestamp));
    }

    /// @notice Merkle Root 기록 (확장 기능, ANCHOR_MODE=merkle)
    function registerRoot(bytes32 merkleRoot) external onlyOwner {
        if (merkleRoot == bytes32(0)) revert EmptyHash();
        if (roots[merkleRoot] != 0) revert AlreadyRegistered();
        roots[merkleRoot] = uint64(block.timestamp);
        emit RootRegistered(merkleRoot, uint64(block.timestamp));
    }

    function get(bytes32 documentHash) external view returns (uint64 timestamp, uint16 version, bool exists) {
        Record memory r = records[documentHash];
        return (r.timestamp, r.version, r.exists);
    }

    function getRoot(bytes32 merkleRoot) external view returns (uint64 timestamp) {
        return roots[merkleRoot];
    }
}
