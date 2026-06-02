module top_module (
    input clk,
    input reset,
    input [1:0] req,
    output [1:0] grant
);
    reg sel;

    always @(posedge clk) begin
        if (reset) begin
            sel <= 1'b0;
        end else if (req == 2'b11) begin
            sel <= ~sel;
        end
    end

    assign grant = (req == 2'b00) ? 2'b00 :
                   (req == 2'b01) ? 2'b01 :
                   (req == 2'b10) ? 2'b10 :
                   (sel ? 2'b10 : 2'b01);
endmodule
