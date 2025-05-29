-- table_flattener.lua
-- HTML 테이블 조각을 처리할 때 셀 내부의 리스트와 단락을 단순화합니다.

-- 블록 리스트를 받아 인라인 리스트로 변환하되, 원래 블록 사이에는 <br /> 삽입
local function blocks_to_inlines_with_br(blocks)
  local inls = pandoc.Inlines{}
  for i, block in ipairs(blocks) do
    if i > 1 and #inls > 0 then -- 이전 인라인 내용이 있다면 <br /> 추가
      inls:insert(pandoc.RawInline('html', '<br />'))
    end
    if block.t == "Para" or block.t == "Plain" then
      for _, inl in ipairs(block.content) do
        inls:insert(inl)
      end
    else
      -- 다른 유형의 블록(예: 중첩 리스트, 코드 블록)은 문자열로 변환
      -- 문자열 변환 전에 이미 인라인 내용이 있다면 공백 추가
      if #inls > 0 and (inls[#inls].t ~= "Space" and inls[#inls].t ~= "SoftBreak") then
           inls:insert(pandoc.Space())
      end
      inls:insert(pandoc.Str(pandoc.utils.stringify(block)))
    end
  end
  return inls
end

-- 리스트 요소(BulletList, OrderedList)를 평탄화하는 공통 로직
local function flatten_list_element(list_el)
  local new_inlines = pandoc.Inlines{}
  for i, item_blocks in ipairs(list_el.content) do -- item_blocks is a list of Blocks for one <li>
    if #new_inlines > 0 then -- 첫 번째 아이템이 아니라면, 이전 아이템과 <br />로 구분
      new_inlines:insert(pandoc.RawInline('html', '<br />'))
    end
    new_inlines:insert(pandoc.Str("- ")) -- 각 아이템 앞에 "- " 접두사 추가
    
    local item_content_inlines = blocks_to_inlines_with_br(item_blocks)
    for _, inl in ipairs(item_content_inlines) do
      new_inlines:insert(inl)
    end
  end

  if #new_inlines > 0 then
    -- 전체를 하나의 Plain 요소로 반환 (셀 내부에 들어갈 내용)
    return pandoc.Plain(new_inlines) 
  else
    -- 리스트가 비어있었다면 아무것도 반환하지 않음 (또는 빈 Plain)
    return pandoc.Plain(pandoc.Inlines{}) 
  end
end

function BulletList(el)
  return flatten_list_element(el)
end

function OrderedList(el)
  return flatten_list_element(el) -- OrderedList도 일단 BulletList처럼 "- "로 시작
end

-- 테이블 셀 내의 단락(Para)을 일반 텍스트(Plain)로 변경
function Para(el)
  return pandoc.Plain(el.content)
end